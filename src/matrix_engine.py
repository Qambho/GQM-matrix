#!/usr/bin/env python3
from __future__ import annotations

import json
import math
import os
import re
import subprocess
import sys
import time
import urllib.request
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from threading import Thread
from typing import Deque, Dict, List, Optional, Sequence, Tuple

# External JSON configuration file for engine tuning
CONFIG_FILE = "config.json"
DEGREE_MULTIPLIER = 1.0

# ANSI Escape Colors for terminal rendering
C_RESET = "\033[0m"
C_BOLD = "\033[1m"
C_RED = "\033[91m"
C_GREEN = "\033[92m"
C_YELLOW = "\033[93m"
C_CYAN = "\033[96m"
C_MAGENTA = "\033[95m"
C_BG_RED = "\033[41m\033[97m"
C_BG_YEL = "\033[43m\033[30m"

RAW_DASHA_DATA = """
   Mars: 2026-06-30 (20:24:49) - 2026-06-30 (20:28:10)
   Merc: 2026-06-30 (20:28:10) - 2026-06-30 (20:35:20)
   Sat: 2026-06-30 (20:35:20) - 2026-06-30 (20:39:35)
   Jup: 2026-06-30 (20:39:35) - 2026-06-30 (20:47:43)
   Rah: 2026-06-30 (20:47:43) - 2026-06-30 (20:52:55)
   Ven: 2026-06-30 (20:52:55) - 2026-06-30 (21:02:05)
   Sun: 2026-06-30 (21:02:05) - 2026-06-30 (21:04:43)
   Moon: 2026-06-30 (21:04:43) - 2026-06-30 (21:11:21)




"""

DEFAULT_ANGLE_MULTIPLIERS = {str(angle): 1.0 for angle in range(0, 360, 45)}

# Global tracking metrics
UPCOMING_TIME_GATES: List[Dict[str, object]] = []
ENGINE_CONFIG: Optional["EngineConfig"] = None
ENGINE_DATA_STREAM: Dict[str, object] = {}
LATEST_BYBIT_ORDERBOOK: Dict[str, object] = {"bids": [], "asks": []}
FROZEN_SIGNAL_LOG: Deque[str] = deque(maxlen=12)
LIQUIDITY_WALL_MULTIPLIER = 3.0
LATEST_BYBIT_ORDERBOOK: Dict[str, List[List[float]]] = {"bids": [], "asks": []}
FROZEN_SIGNAL_LOG: Deque[str] = deque(maxlen=12)
LIQUIDITY_WALL_MULTIPLIER = 3.0

NAKSHATRAS = [
    "Ashwini", "Bharani", "Krittika", "Rohini", "Mrigashira", "Ardra",
    "Punarvasu", "Pushya", "Ashlesha", "Magha", "Purva Phalguni", "Uttara Phalguni",
    "Hasta", "Chitra", "Swati", "Vishakha", "Anuradha", "Jyeshtha", "Mula",
    "Purva Ashadha", "Uttara Ashadha", "Shravana", "Dhanishta", "Shatabhisha",
    "Purva Bhadrapada", "Uttara Bhadrapada", "Revati"
]

@dataclass(frozen=True)
class PricePoint:
    """A timestamped market price used for volatility calibration."""
    timestamp: float
    price: float

@dataclass(frozen=True)
class EngineConfig:
    """External configuration for anchor, volatility, alert settings, and multiplier vectors."""
    anchor_price: float = 95000.0
    atr_window_seconds: int = 600
    flanking_coefficient: float = 0.0001
    alert_enabled: bool = False
    min_scale: float = 0.5
    max_scale: float = 150.0
    dynamic_anchor_window_seconds: int = 14400
    angle_multipliers: Dict[str, float] = field(default_factory=lambda: dict(DEFAULT_ANGLE_MULTIPLIERS))

    @classmethod
    def from_dict(cls, data: Dict[str, object]) -> "EngineConfig":
        def normalize_angle_multipliers(raw_value: object) -> Dict[str, float]:
            defaults = dict(DEFAULT_ANGLE_MULTIPLIERS)
            if not isinstance(raw_value, dict):
                return defaults

            normalized: Dict[str, float] = {}
            for angle_key, coefficient in raw_value.items():
                try:
                    angle_int = int(str(angle_key))
                except (TypeError, ValueError):
                    continue
                if angle_int % 45 != 0 or angle_int < 0 or angle_int >= 360:
                    continue
                try:
                    normalized[str(angle_int)] = float(coefficient)
                except (TypeError, ValueError):
                    continue

            if not normalized:
                return defaults
            merged = defaults.copy()
            merged.update(normalized)
            return merged

        return cls(
            anchor_price=float(data.get("anchor_price", cls.__dataclass_fields__["anchor_price"].default)),
            atr_window_seconds=int(data.get("atr_window_seconds", cls.__dataclass_fields__["atr_window_seconds"].default)),
            flanking_coefficient=float(data.get("flanking_coefficient", cls.__dataclass_fields__["flanking_coefficient"].default)),
            alert_enabled=bool(data.get("alert_enabled", cls.__dataclass_fields__["alert_enabled"].default)),
            min_scale=float(data.get("min_scale", cls.__dataclass_fields__["min_scale"].default)),
            max_scale=float(data.get("max_scale", cls.__dataclass_fields__["max_scale"].default)),
            dynamic_anchor_window_seconds=int(data.get("dynamic_anchor_window_seconds", cls.__dataclass_fields__["dynamic_anchor_window_seconds"].default)),
            angle_multipliers=normalize_angle_multipliers(data.get("angle_multipliers")),
        )

    def to_dict(self) -> Dict[str, object]:
        return {
            "anchor_price": self.anchor_price,
            "atr_window_seconds": self.atr_window_seconds,
            "flanking_coefficient": self.flanking_coefficient,
            "alert_enabled": self.alert_enabled,
            "min_scale": self.min_scale,
            "max_scale": self.max_scale,
            "dynamic_anchor_window_seconds": self.dynamic_anchor_window_seconds,
            "angle_multipliers": self.angle_multipliers or dict(DEFAULT_ANGLE_MULTIPLIERS),
        }


def load_config(config_path: str = CONFIG_FILE) -> EngineConfig:
    """Load engine tuning variables from JSON without hardcoding them in the script."""
    config_file = Path(config_path)
    if not config_file.exists():
        return EngineConfig()

    try:
        raw = json.loads(config_file.read_text())
        if not isinstance(raw, dict):
            return EngineConfig()
        return EngineConfig.from_dict(raw)
    except (OSError, ValueError):
        return EngineConfig()


def parse_jagannatha_hora_block(raw_data: Optional[str] = None) -> None:
    """Automatically cleans and maps raw JH Ashtottari Dasa text to the 3-6-9 matrix system."""
    global UPCOMING_TIME_GATES, RAW_DASHA_DATA
    if raw_data is not None:
        RAW_DASHA_DATA = raw_data
    UPCOMING_TIME_GATES = []
    root_map = {
        "sun": 3, "mars": 3, "jup": 3,
        "moon": 6, "rah": 6, "sat": 6,
        "merc": 9, "ven": 9
    }
    lines = RAW_DASHA_DATA.strip().split("\n")
    for line in lines:
        match = re.search(r"(\w+):\s*([\d-]+)\s*\(([\d:]+)\)", line)
        if match:
            lord_name = match.group(1)
            date_part = match.group(2)
            time_part = match.group(3)
            norm_key = lord_name.lower()[:4]
            assigned_root = 0
            for key, val in root_map.items():
                if key.startswith(norm_key) or norm_key.startswith(key):
                    assigned_root = val
                    break
            if assigned_root != 0:
                UPCOMING_TIME_GATES.append({
                    "time": f"{date_part} {time_part}",
                    "dasha_lord": lord_name,
                    "root": assigned_root
                })


def calculate_current_nakshatra() -> Tuple[str, int]:
    """Calculates the active lunar Nakshatra step based on sidereal mean cycles."""
    now_epoch = time.time()
    sidereal_month_seconds = 2360591.5
    known_moon_anchor = 1717180800

    elapsed_seconds = now_epoch - known_moon_anchor
    current_cycle_position = (elapsed_seconds / sidereal_month_seconds) % 1.0
    moon_longitude = current_cycle_position * 360.0

    nakshatra_index = int(moon_longitude / (360.0 / 27.0)) % 27
    pada_index = int((moon_longitude % (360.0 / 27.0)) / (360.0 / 108.0)) % 4 + 1
    return NAKSHATRAS[nakshatra_index], pada_index


def get_binance_price() -> Tuple[Optional[float], Optional[str]]:
    url = "https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=1.5) as response:
            data = json.loads(response.read().decode())
            return float(data["price"]), data["price"]
    except Exception:
        return None, None


def get_digital_root(price_str: str) -> int:
    digits = "".join(c for c in price_str if c.isdigit())
    if not digits:
        return 0
    total = sum(int(d) for d in digits)
    while total > 9:
        total = sum(int(d) for d in str(total))
    return total


def append_price_point(history: Deque[PricePoint], price: float) -> None:
    """Add the latest price quote to the ATR volatility queue."""
    history.append(PricePoint(timestamp=time.time(), price=price))


def calculate_average_true_range(price_points: Sequence[PricePoint], window_seconds: int) -> float:
    """Compute ATR over a recent window of price movement magnitudes."""
    if len(price_points) < 2:
        return 0.0

    end_time = price_points[-1].timestamp
    window = [point for point in price_points if point.timestamp >= end_time - window_seconds]
    if len(window) < 2:
        return 0.0

    true_ranges: List[float] = []
    previous_price = window[0].price
    for point in window[1:]:
        true_ranges.append(abs(point.price - previous_price))
        previous_price = point.price

    if not true_ranges:
        return 0.0
    return sum(true_ranges) / len(true_ranges)


def calculate_price_per_degree_scale(
    price_points: Sequence[PricePoint], window_seconds: int, config: EngineConfig
) -> float:
    """Auto-calibrate the Astro-Line scale using ATR-based volatility."""
    atr = calculate_average_true_range(price_points, window_seconds)
    if atr <= 0.0:
        return max(config.min_scale, 1.0)

    scale = atr / 10.0
    return max(config.min_scale, min(scale, config.max_scale))


def fetch_binance_ohlcv(symbol: str = "BTCUSDT", interval: str = "1h", limit: int = 4) -> List[List[object]]:
    url = (
        f"https://api.binance.com/api/v3/klines?symbol={symbol}"
        f"&interval={interval}&limit={limit}"
    )
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=3.0) as response:
            data = json.loads(response.read().decode())
            if isinstance(data, list):
                return data
    except Exception:
        pass
    return []


def calculate_next_anchor_refresh(now: float) -> float:
    current = datetime.fromtimestamp(now)
    boundary_hour = (current.hour // 4) * 4
    next_boundary = current.replace(
        hour=boundary_hour,
        minute=0,
        second=0,
        microsecond=0,
    ) + timedelta(hours=4)
    return next_boundary.timestamp()


def auto_refresh_anchor(
    current_anchor: float,
    config: EngineConfig,
    next_refresh_at: float,
) -> Tuple[float, float]:
    """Refresh the anchor every 4 hours using the last 4h OHLCV lows."""
    now = time.time()
    if now < next_refresh_at:
        return current_anchor, next_refresh_at

    candles = fetch_binance_ohlcv("BTCUSDT", "1h", 4)
    lows = [float(candle[3]) for candle in candles if len(candle) >= 5]
    new_anchor = min(lows) if lows else current_anchor
    if new_anchor != current_anchor:
        print(f"[SYSTEM] Anchor reset to {new_anchor:,.2f} based on 4H rolling low")
    next_refresh_at = calculate_next_anchor_refresh(now)
    return new_anchor, next_refresh_at


def get_dynamic_anchor(
    current_price: float,
    price_points: Sequence[PricePoint],
    base_anchor: float,
    window_seconds: int,
    price_per_degree_scale: float,
    angle_multipliers: Dict[str, float],
) -> float:
    """Return a rolling 4-hour low anchor and align it so 0° is closest to spot."""
    if price_per_degree_scale <= 0 or not price_points:
        return base_anchor

    now = time.time()
    window = [point.price for point in price_points if point.timestamp >= now - window_seconds]
    if not window:
        return base_anchor

    anchor = min(window)
    multipliers = angle_multipliers or dict(DEFAULT_ANGLE_MULTIPLIERS)
    sorted_angles = sorted(int(angle_str) for angle_str in multipliers.keys())
    if len(sorted_angles) < 2:
        return anchor

    angle_steps = [
        sorted_angles[i + 1] - sorted_angles[i]
        for i in range(len(sorted_angles) - 1)
    ]
    angle_steps.append((sorted_angles[0] + 360) - sorted_angles[-1])
    step_angle = min(angle_steps)
    step_distance = step_angle * price_per_degree_scale
    if step_distance <= 0:
        return anchor

    distance = current_price - anchor
    shifts = int(round(distance / step_distance))
    anchor += shifts * step_distance

    return anchor


def update_bybit_orderbook(
    bids: Sequence[Sequence[float] | Tuple[float, float]],
    asks: Sequence[Sequence[float] | Tuple[float, float]],
) -> None:
    """Ingest live Bybit order book depth for liquidity wall confluence."""
    global LATEST_BYBIT_ORDERBOOK
    LATEST_BYBIT_ORDERBOOK = {
        "bids": [(float(level[0]), float(level[1])) for level in bids[:50]],
        "asks": [(float(level[0]), float(level[1])) for level in asks[:50]],
    }


def _normalize_book_levels(levels: object) -> List[Tuple[float, float]]:
    normalized: List[Tuple[float, float]] = []
    if not isinstance(levels, (list, tuple)):
        return normalized
    for item in levels:
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            normalized.append((float(item[0]), float(item[1])))
        elif isinstance(item, dict):
            price = item.get("price", item.get("p"))
            qty = item.get("qty", item.get("v", item.get("size")))
            if price is not None and qty is not None:
                normalized.append((float(price), float(qty)))
    return normalized[:50]


def analyze_orderbook_depth(data: Dict[str, object]) -> List[Dict[str, object]]:
    """Detect 3x+ average volume clusters in the top 50 bid/ask levels."""
    bids = _normalize_book_levels(data.get("bids"))
    asks = _normalize_book_levels(data.get("asks"))
    combined = bids + asks
    if not combined:
        return []

    avg_volume = sum(volume for _, volume in combined) / len(combined)
    if avg_volume <= 0:
        return []

    threshold = avg_volume * LIQUIDITY_WALL_MULTIPLIER
    walls: List[Dict[str, object]] = []
    for side, levels in (("bid", bids), ("ask", asks)):
        for price, volume in levels:
            if volume >= threshold:
                walls.append(
                    {
                        "price": float(price),
                        "volume": float(volume),
                        "side": side,
                        "classification": "LIQUIDITY_WALL",
                    }
                )
    return walls


def get_linear_multiplier_nodes(
    current_price: float,
    anchor_price: float,
    angle_multipliers: Dict[str, float],
    price_per_degree_scale: float,
    adaptive_tolerance: float = 0.0,
    orderbook_data: Optional[Dict[str, object]] = None,
) -> Tuple[List[Tuple[float, int]], float, List[Dict[str, object]]]:
    """Generates linear nodes and flags liquidity-wall confluence within adaptive tolerance."""
    levels: List[Tuple[float, int]] = []
    node_confluence: List[Dict[str, object]] = []
    step = 45.0 * DEGREE_MULTIPLIER
    book = orderbook_data if orderbook_data is not None else LATEST_BYBIT_ORDERBOOK
    liquidity_walls = analyze_orderbook_depth(book)

    for angle in range(0, 360, 45):
        price_level = anchor_price + ((angle / 45.0) * step)
        levels.append((price_level, angle))

        node_entry: Dict[str, object] = {
            "angle": angle,
            "price": float(price_level),
            "support_wall": None,
            "resistance_wall": None,
        }
        for wall in liquidity_walls:
            if abs(float(wall["price"]) - price_level) > adaptive_tolerance:
                continue
            if wall["side"] == "bid":
                node_entry["support_wall"] = {
                    "price": wall["price"],
                    "volume": wall["volume"],
                    "classification": "SUPPORT_WALL",
                }
            elif wall["side"] == "ask":
                node_entry["resistance_wall"] = {
                    "price": wall["price"],
                    "volume": wall["volume"],
                    "classification": "RESISTANCE_WALL",
                }
        node_confluence.append(node_entry)

    nearest_distance = min(abs(current_price - price_level) for price_level, _ in levels)
    return levels, nearest_distance, node_confluence


def get_true_astro_gate():
    current_utc_timestamp = int(time.time())
    for gate in UPCOMING_TIME_GATES:
        try:
            gate_epoch = int(datetime.strptime(gate["time"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).timestamp())
            if gate_epoch > current_utc_timestamp:
                return gate_epoch - current_utc_timestamp, gate["root"], gate["dasha_lord"]
        except ValueError:
            continue
    remaining = 180 - (current_utc_timestamp % 180)
    fallback_root = [3, 6, 9][int((current_utc_timestamp // 180) % 3)]
    return remaining, fallback_root, "Dynamic-Loop"

def analyze_wave_structure(history):
    if len(history) < 4:
        return "INITIALIZING ENGINE...", "NEUTRAL"
    p0, p1, p2, p3 = history[0], history[1], history[2], history[3]
    if p0 > p1 and p1 < p2 and p2 > p3 and p3 > p1:
        return "W-WAVE (BULLISH ACCUMULATION)", "BULLISH"
    if p0 < p1 and p1 > p2 and p2 < p3 and p3 < p1:
        return "M-WAVE (BEARISH EXHAUSTION)", "BEARISH"
    return "CONSOLIDATING LINEAR FLOW", "NEUTRAL"

def trigger_android_hardware_alert(target_level, angle):
    """Triggers Android alerts with strict timeouts to prevent OS thread freezing."""
    try:
        subprocess.run(
            ["termux-vibrate", "-d", "400"], 
            stdout=subprocess.DEVNULL, 
            stderr=subprocess.DEVNULL, 
            timeout=0.5
        )
        msg = f"Target Level: {target_level:,.2f} at Angle: {angle}°"
        subprocess.run(
            ["termux-notification", "--title", "🚨 MATRIX TRIPLE CONFLUENCE 🚨", "--content", msg, "--priority", "high"], 
            stdout=subprocess.DEVNULL, 
            stderr=subprocess.DEVNULL, 
            timeout=0.5
        )
    except subprocess.TimeoutExpired:
        pass
    except Exception:
        sys.stdout.write("\a")
        sys.stdout.flush()


def trigger_trade_notification(title: str, content: str, ongoing: bool = True, nid: int = 999) -> None:
    """Send a persistent trade notification via Termux (kept separate from math logic).

    Kept as a separate helper so the computation engine can be tested without Android
    dependencies by stubbing or disabling this function.
    """
    try:
        args = [
            "termux-notification",
            "--title",
            title,
            "--content",
            content,
            "--priority",
            "high",
            "--id",
            str(nid),
        ]
        if ongoing:
            args.append("--ongoing")

        subprocess.run(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=1.0)
    except Exception:
        # Non-fatal on non-Android hosts
        pass


def send_alert(title: str, content: str, ongoing: bool = True, nid: int = 999) -> None:
    """Send a local fallback notification via Termux if available."""
    trigger_trade_notification(title, content, ongoing=ongoing, nid=nid)


def clear_screen() -> None:
    os.system("cls" if os.name == "nt" else "clear")


class MatrixAPIHandler(BaseHTTPRequestHandler):
    def _send_json(self, status_code: int, payload: dict) -> None:
        self.send_response(status_code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
        self.wfile.write(json.dumps(payload).encode('utf-8'))

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_GET(self) -> None:
        if self.path == '/api/metrics':
            self._send_json(200, ENGINE_DATA_STREAM)
        else:
            self._send_json(404, {'status': 'error', 'message': 'Route not found'})

    def do_POST(self) -> None:
        content_length = int(self.headers.get('Content-Length', 0))
        raw_body = self.rfile.read(content_length).decode('utf-8', errors='replace')

        try:
            payload = json.loads(raw_body)
        except json.JSONDecodeError:
            self._send_json(400, {'status': 'error', 'message': 'Invalid JSON structure'})
            return

        if self.path == '/api/update-dasa':
            raw_dasa = payload.get('raw_dasa')
            if not isinstance(raw_dasa, str) or not raw_dasa.strip():
                self._send_json(400, {'status': 'error', 'message': 'raw_dasa string required'})
                return
            try:
                parse_jagannatha_hora_block(raw_dasa)
                self._send_json(200, {'status': 'success', 'message': 'Dasa timelines synchronized'})
            except Exception as exc:
                self._send_json(500, {'status': 'error', 'message': str(exc)})

        elif self.path == '/api/config-override':
            global ENGINE_CONFIG
            try:
                if isinstance(payload, dict):
                    updated_config = EngineConfig.from_dict(payload)
                    ENGINE_CONFIG = updated_config
                    with open(CONFIG_FILE, 'w', encoding='utf-8') as handle:
                        json.dump(updated_config.to_dict(), handle, indent=2)
                    self._send_json(200, {'status': 'success', 'message': 'Engine configuration mutated'})
                else:
                    self._send_json(400, {'status': 'error', 'message': 'Configuration payload must be an object'})
            except Exception as exc:
                self._send_json(500, {'status': 'error', 'message': str(exc)})
        else:
            self._send_json(404, {'status': 'error', 'message': 'Route not found'})


def run_api_server() -> None:
    server = HTTPServer(('0.0.0.0', 5000), MatrixAPIHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def main() -> None:
    global ENGINE_CONFIG
    ENGINE_CONFIG = load_config()
    config = ENGINE_CONFIG
    parse_jagannatha_hora_block()
    clear_screen()
    price_history: Deque[float] = deque(maxlen=4)
    price_points: Deque[PricePoint] = deque()
    anchor_price = config.anchor_price
    next_refresh_at = calculate_next_anchor_refresh(time.time())
    active_trade: Dict[str, object] = {"status": "IDLE"}
    # track if we've already warned about stalling for the active trade
    # and a unique notification id (kept constant for persistence)
    trade_notification_id = 999

    while True:
        price_flt, price_str = get_binance_price()

        # FIX: Handle network dropouts explicitly without terminal display locking
        if price_flt is None:
            clear_screen()
            print(f"{C_BOLD}{C_CYAN}============================================================{C_RESET}")
            print(f"  {C_BG_RED} ⚠️  MATRIX ENGINE WARNING: DATA STREAM PAUSED  ⚠️ {C_RESET}")
            print(f"{C_BOLD}{C_CYAN}============================================================{C_RESET}")
            print(f"  {C_RED}Status:{C_RESET} Re-establishing contact with Binance REST API...")
            print(f"  {C_YELLOW}Action:{C_RESET} Keeping interface coordinates frozen safely. Standby.")
            print(f"{C_BOLD}{C_CYAN}============================================================{C_RESET}")
            time.sleep(1.5)
            continue

        append_price_point(price_points, price_flt)
        price_history.append(price_flt)
        anchor_price, next_refresh_at = auto_refresh_anchor(
            anchor_price,
            config,
            next_refresh_at,
        )

        price_root = get_digital_root(price_str)
        price_per_degree_scale = calculate_price_per_degree_scale(
            price_points, config.atr_window_seconds, config
        )
        config = ENGINE_CONFIG or load_config()
        angle_multipliers = config.angle_multipliers or dict(DEFAULT_ANGLE_MULTIPLIERS)
        dynamic_anchor = get_dynamic_anchor(
            price_flt,
            price_points,
            anchor_price,
            config.dynamic_anchor_window_seconds,
            price_per_degree_scale,
            angle_multipliers,
        )
        dynamic_tolerance = price_flt * config.flanking_coefficient
        proximity_warning_zone = dynamic_tolerance * 5.0
        gann_levels, nearest_node_distance, node_confluence = get_linear_multiplier_nodes(
            price_flt,
            dynamic_anchor,
            angle_multipliers,
            price_per_degree_scale,
            adaptive_tolerance=dynamic_tolerance,
        )
        liquidity_walls = analyze_orderbook_depth(LATEST_BYBIT_ORDERBOOK)
        countdown, astro_root, active_lord = get_true_astro_gate()
        wave_status, bias = analyze_wave_structure(price_history)
        nak_name, nak_pada = calculate_current_nakshatra()

        near_gann_level = None
        incoming_signal = False
        target_proximity_lvl = None
        proximity_percentage = 0

        for lvl_price, angle in gann_levels:
            distance = abs(price_flt - lvl_price)
            if distance <= dynamic_tolerance:
                near_gann_level = (lvl_price, angle)
                break
            elif distance <= proximity_warning_zone:
                incoming_signal = True
                target_proximity_lvl = (lvl_price, angle)
                proximity_percentage = int((1.0 - (distance / proximity_warning_zone)) * 100)
                break

        is_360_root = price_root in [3, 6, 9]
        is_time_gate_open = countdown <= 15 or countdown >= 165

        active_liquidity_wall = None
        if near_gann_level is not None:
            hit_price, _ = near_gann_level
            for wall in liquidity_walls:
                if abs(float(wall["price"]) - hit_price) <= dynamic_tolerance:
                    active_liquidity_wall = wall
                    break

        triple_confluence = is_360_root and near_gann_level is not None and is_time_gate_open
        quadruple_confluence = triple_confluence and active_liquidity_wall is not None
        standard_signal = is_360_root and not triple_confluence

        # Trade entry logic: create an active_trade when triple_confluence occurs
        if triple_confluence and active_trade.get("status") != "ACTIVE":
            # Normalize node list ascending by price to index safely
            nodes_sorted = sorted(gann_levels, key=lambda x: x[0])
            # find closest index to the triggered level
            triggered_price = near_gann_level[0]
            idx = min(range(len(nodes_sorted)), key=lambda i: abs(nodes_sorted[i][0] - triggered_price))

            entry_price, entry_angle = nodes_sorted[idx]

            # Helper to compute fallback cardinal nodes if index near boundaries
            def cardinal_price_for(angle: int) -> float:
                return anchor_price + (angle * price_per_degree_scale)

            # Determine TP1, TP2, SL with boundary checks
            tp1 = nodes_sorted[idx + 1][0] if idx + 1 < len(nodes_sorted) else cardinal_price_for(90)
            tp2 = nodes_sorted[idx + 2][0] if idx + 2 < len(nodes_sorted) else cardinal_price_for(180)
            prev_node = nodes_sorted[idx - 1][0] if idx - 1 >= 0 else cardinal_price_for(360)

            # Adaptive tolerance buffer for SL
            if tp1 > entry_price:
                side = "LONG"
                sl = prev_node - dynamic_tolerance
            else:
                side = "SHORT"
                sl = prev_node + dynamic_tolerance

            active_trade = {
                "status": "ACTIVE",
                "entry": float(entry_price),
                "entry_angle": int(entry_angle),
                "tp1": float(tp1),
                "tp2": float(tp2),
                "sl": float(sl),
                "side": side,
                "start_price": float(price_flt),
                "start_time": time.time(),
                "stall_warned": False,
            }

            if config.alert_enabled:
                send_alert(
                    "Trade ACTIVE",
                    f"Entry: {active_trade['entry']:,.2f} | TP1: {active_trade['tp1']:,.2f} | TP2: {active_trade['tp2']:,.2f} | SL: {active_trade['sl']:,.2f}",
                    ongoing=True,
                    nid=trade_notification_id,
                )

        elif is_360_root and not triple_confluence:
            standard_signal = True

        misalignment_warning = None
        if nearest_node_distance > 500:
            misalignment_warning = (
                f"{C_YELLOW}WARNING: Grid Anchor is misaligned — nearest node is "
                f"{nearest_node_distance:.0f} away. Update your baseline.{C_RESET}"
            )

        # Determine Reversal Characteristics
        reversal_type = "NEUTRAL EXHAUSTION NODE"
        if near_gann_level or target_proximity_lvl:
            active_node = near_gann_level if near_gann_level else target_proximity_lvl
            if bias == "BULLISH" and price_flt <= active_node[0]:
                reversal_type = f"{C_GREEN}POTENTIAL BULLISH REVERSAL (LONG ENTRY ZONE){C_RESET}"
            elif bias == "BEARISH" and price_flt >= active_node[0]:
                reversal_type = f"{C_RED}POTENTIAL BEARISH REVERSAL (SHORT EXHAUSTION ZONE){C_RESET}"

        # Trade monitoring: update active_trade state based on live price
        if active_trade.get("status") == "ACTIVE":
            et = active_trade
            side = et.get("side")
            entry = float(et.get("entry"))
            tp1 = float(et.get("tp1"))
            tp2 = float(et.get("tp2"))
            sl = float(et.get("sl"))

            # LONG side monitoring
            if side == "LONG":
                if price_flt >= tp1 and et["status"] == "ACTIVE":
                    et["status"] = "TP1_HIT"
                    if config.alert_enabled:
                        send_alert("TP1 HIT", f"TP1 hit at {price_flt:,.2f}", ongoing=True, nid=trade_notification_id)
                if price_flt >= tp2 and et["status"] in ("ACTIVE", "TP1_HIT"):
                    et["status"] = "TP2_HIT"
                    if config.alert_enabled:
                        send_alert("TP2 HIT", f"TP2 hit at {price_flt:,.2f}", ongoing=True, nid=trade_notification_id)
                if price_flt <= sl and et["status"] not in ("SL_HIT",):
                    et["status"] = "SL_HIT"
                    if config.alert_enabled:
                        send_alert("SL HIT", f"Stop hit at {price_flt:,.2f}", ongoing=True, nid=trade_notification_id)
                # Warning: 1% adverse without SL
                if not et.get("stall_warned") and price_flt < entry * 0.99 and price_flt > sl:
                    et["stall_warned"] = True
                    if config.alert_enabled:
                        send_alert("WARNING: Trade Stalling", f"Price {price_flt:,.2f} down >1% from entry {entry:,.2f}", ongoing=True, nid=trade_notification_id)

            # SHORT side monitoring
            if side == "SHORT":
                if price_flt <= tp1 and et["status"] == "ACTIVE":
                    et["status"] = "TP1_HIT"
                    if config.alert_enabled:
                        send_alert("TP1 HIT", f"TP1 hit at {price_flt:,.2f}", ongoing=True, nid=trade_notification_id)
                if price_flt <= tp2 and et["status"] in ("ACTIVE", "TP1_HIT"):
                    et["status"] = "TP2_HIT"
                    if config.alert_enabled:
                        send_alert("TP2 HIT", f"TP2 hit at {price_flt:,.2f}", ongoing=True, nid=trade_notification_id)
                if price_flt >= sl and et["status"] not in ("SL_HIT",):
                    et["status"] = "SL_HIT"
                    if config.alert_enabled:
                        send_alert("SL HIT", f"Stop hit at {price_flt:,.2f}", ongoing=True, nid=trade_notification_id)
                # Warning: 1% adverse without SL for shorts
                if not et.get("stall_warned") and price_flt > entry * 1.01 and price_flt < sl:
                    et["stall_warned"] = True
                    if config.alert_enabled:
                        send_alert("WARNING: Trade Stalling", f"Price {price_flt:,.2f} up >1% from entry {entry:,.2f}", ongoing=True, nid=trade_notification_id)

        clear_screen()
        print(f"{C_BOLD}{C_CYAN}============================================================{C_RESET}")
        print(f"  GEO-QUANTUM ENGINE V4 (PRODUCTION BUILD)       {datetime.now(timezone.utc).strftime('%H:%M:%S')} UTC")
        print(f"{C_BOLD}{C_CYAN}============================================================{C_RESET}")
        print(f"  {C_BOLD}ASSET TICKER:{C_RESET} BTCUSDT")
        print(f"  {C_BOLD}SPOT PRICE  :{C_RESET} {C_CYAN}{price_flt:,.2f}{C_RESET}")
        print(f"  {C_BOLD}WAVE PHASING:{C_RESET} {C_BOLD}{C_YELLOW}{wave_status}{C_RESET}")
        print(f"  {C_BOLD}NAKSHATRA   :{C_RESET} {C_MAGENTA}{nak_name} (Pada {nak_pada}){C_RESET}")
        print(f"------------------------------------------------------------")
        
        root_color = C_GREEN if is_360_root else C_RESET
        print(f"  {C_BOLD}PRICE ROOT  :{C_RESET} {root_color}[{price_root}]{C_RESET}")
        print(f"  {C_BOLD}DASHA ROOT  :{C_RESET} {C_YELLOW}[{astro_root}] ({active_lord}){C_RESET}")
        
        hours, remainder = divmod(int(countdown), 3600)
        mins, secs = divmod(remainder, 60)
        time_color = C_RED if is_time_gate_open else C_GREEN
        print(f"  {C_BOLD}DASHA TRANSITION COUNTDOWN:{C_RESET} {time_color}{hours:02d}:{mins:02d}:{secs:02d}{C_RESET}")
        print(f"{C_CYAN}------------------------------------------------------------{C_RESET}")
        
        print(f"  {C_BOLD}LOCAL LINEAR NODES (Adaptive Tol: ±{dynamic_tolerance:.2f}){C_RESET}")
        confluence_by_angle = {int(entry["angle"]): entry for entry in node_confluence}
        for lvl_price, angle in sorted(gann_levels, reverse=True):
            is_hit = abs(price_flt - lvl_price) <= dynamic_tolerance
            marker = f" {C_GREEN}◄◄ CRITICAL NODE HIT{C_RESET}" if is_hit else ""
            wall_marker = ""
            node_flags = confluence_by_angle.get(angle, {})
            support_wall = node_flags.get("support_wall")
            resistance_wall = node_flags.get("resistance_wall")
            if support_wall:
                wall_marker = (
                    f" {C_GREEN}| SUPPORT_WALL {float(support_wall['volume']):.4f} BTC{C_RESET}"
                )
            elif resistance_wall:
                wall_marker = (
                    f" {C_RED}| RESISTANCE_WALL {float(resistance_wall['volume']):.4f} BTC{C_RESET}"
                )
            print(f"    Node Angle {angle:3}°: {lvl_price:10,.2f}{marker}{wall_marker}")

        print(f"{C_CYAN}------------------------------------------------------------{C_RESET}")

        # Signal Rendering Dashboard
        if quadruple_confluence:
            wall_volume = float(active_liquidity_wall["volume"])
            log_line = (
                f"{datetime.now(timezone.utc).strftime('%H:%M:%S')} "
                f"| LIQUIDITY WALL ACTIVE | Size: {wall_volume:.4f} BTC"
            )
            if not FROZEN_SIGNAL_LOG or FROZEN_SIGNAL_LOG[-1] != log_line:
                FROZEN_SIGNAL_LOG.append(log_line)
            print(f"  {C_BG_RED} 🔥🔥🔥🔥 QUADRUPLE CONFLUENCE DETECTED 🔥🔥🔥🔥 {C_RESET}")
            print(f"  CHARACTER: {reversal_type}")
            print(
                f"  Target Level: {near_gann_level[0]:,.2f} | Angle: {near_gann_level[1]}° "
                f"| LIQUIDITY WALL ACTIVE | Size: {wall_volume:.4f} BTC"
            )
        elif triple_confluence:
            print(f"  {C_BG_RED} 🔥🔥🔥 TRIPLE CONFLUENCE DETECTED 🔥🔥🔥 {C_RESET}")
            print(f"  CHARACTER: {reversal_type}")
            print(f"  Target Level: {near_gann_level[0]:,.2f} | Angle: {near_gann_level[1]}°")
        elif incoming_signal:
            bars = int(proximity_percentage / 10)
            meter = f"[{'|' * bars}{'.' * (10 - bars)}]"
            print(f"  {C_BG_YEL} 📡 INCOMING HARMONIC SIGNAL {meter} {proximity_percentage}% {C_RESET}")
            print(f"  Approaching Angle {target_proximity_lvl[1]}° Node at {target_proximity_lvl[0]:,.2f} (Distance: ${abs(price_flt - target_proximity_lvl[0]):.2f})")
            print(f"  CHARACTER: {reversal_type}")
        elif standard_signal:
            print(f"  {C_YELLOW} ⚡ STANDARD 3-6-9 VIBRATION ALIGNMENT ⚡ {C_RESET}")
        else:
            print(f"    [ No Active Matrix Convergence ]")

        if FROZEN_SIGNAL_LOG:
            print(f"{C_CYAN}------------------------------------------------------------{C_RESET}")
            print(f"  {C_BOLD}FROZEN SIGNAL LOG:{C_RESET}")
            for line in FROZEN_SIGNAL_LOG:
                print(f"    {line}")

        # Stream compilation for API delivery
        global ENGINE_DATA_STREAM
        ENGINE_DATA_STREAM = {
            "timestamp": time.time(),
            "spot_price": price_flt,
            "price_root": price_root,
            "dasha_root": astro_root,
            "dasha_lord": active_lord,
            "countdown": countdown,
            "wave_status": wave_status,
            "bias": bias,
            "nakshatra": f"{nak_name} (Pada {nak_pada})",
            "scale": price_per_degree_scale,
            "anchor": dynamic_anchor,
            "nodes": [
                (
                    lambda lvl, ang, conf: {
                        "price": lvl,
                        "angle": ang,
                        **(
                            {"support_wall": conf["support_wall"]}
                            if conf.get("support_wall")
                            else {}
                        ),
                        **(
                            {"resistance_wall": conf["resistance_wall"]}
                            if conf.get("resistance_wall")
                            else {}
                        ),
                    }
                )(lvl, ang, conf)
                for (lvl, ang), conf in zip(gann_levels, node_confluence)
            ],
            "liquidity_walls": liquidity_walls,
            "node_confluence": node_confluence,
            "active_liquidity_wall": active_liquidity_wall,
            "active_trade": active_trade,
            "triple_confluence": triple_confluence,
            "quadruple_confluence": quadruple_confluence,
            "signal_log": list(FROZEN_SIGNAL_LOG),
        }

        print(f"{C_BOLD}{C_CYAN}============================================================{C_RESET}")
        time.sleep(0.7)

if __name__ == "__main__":
    api_thread = Thread(target=run_api_server, daemon=True)
    api_thread.start()

    try:
        main()
    except KeyboardInterrupt:
        print(f"\n{C_RED}Engine offline.{C_RESET}")
        sys.exit(0)