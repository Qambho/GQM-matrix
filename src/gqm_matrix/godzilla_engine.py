"""Godzilla V4 MW Advanced Vector Engine — live telemetry + Ashtottari lattice."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable

import pandas as pd
import requests
import websockets

from gqm_matrix.celestial_aspects import analyze_confluence, degree_to_sign
from gqm_matrix.celestial_ephemeris import celestial_snapshot
from gqm_matrix.dynamic_ppd import (
    DEFAULT_ATR_PERIOD,
    DEFAULT_MAX_PPD,
    DEFAULT_MIN_PPD,
    MOON_VELOCITY_5M,
    calculate_dynamic_ppd,
)
from gqm_matrix.lattice_band import (
    build_harmonic_nodes,
    lattice_extremes_from_primary,
    lattice_extremes_meta,
)
from gqm_matrix.mw_anchor import (
    FrozenSwingAnchor,
    build_frozen_swing_anchor,
    build_mw_vertices,
    validate_anchor_prices,
)
from gqm_matrix.spoof_detector import SpoofDetector
from gqm_matrix.vortex import vortex_flags

logger = logging.getLogger("GodzillaEngine")

BINANCE_FUTURES_KLINES = "https://fapi.binance.com/fapi/v1/klines"
BINANCE_FUTURES_WS = "wss://fstream.binance.com/stream"

GRID_SCALING_FACTOR = 0.1
ANCHOR_INTERVAL = "5m"
REVERSAL_ATR_FRACTION = 0.10


class AshtottariVectorMap:
    def __init__(self) -> None:
        self.dasa_map = {
            "Ardra": "Sun",
            "Punarvasu": "Sun",
            "Pushya": "Sun",
            "Ashlesha": "Sun",
            "Magha": "Moon",
            "Purva Phalguni": "Moon",
            "Uttara Phalguni": "Moon",
            "Hasta": "Moon",
            "Chitra": "Mars",
            "Swati": "Mars",
            "Vishakha": "Mars",
            "Anuradha": "Mars",
            "Jyeshtha": "Mercury",
            "Mula": "Mercury",
            "Purva Ashadha": "Mercury",
            "Uttara Ashadha": "Mercury",
            "Abhijit": "Saturn",
            "Shravana": "Saturn",
            "Dhanishta": "Saturn",
            "Shatabhisha": "Saturn",
            "Purva Bhadrapada": "Jupiter",
            "Uttara Bhadrapada": "Jupiter",
            "Revati": "Jupiter",
            "Ashwini": "Rahu",
            "Bharani": "Rahu",
            "Krittika": "Rahu",
            "Rohini": "Venus",
            "Mrigashirsha": "Venus",
        }

        self.boundaries = [
            ("Ashwini", 0.0, 13.33),
            ("Bharani", 13.33, 26.66),
            ("Krittika", 26.66, 40.0),
            ("Rohini", 40.0, 53.33),
            ("Mrigashirsha", 53.33, 66.66),
            ("Ardra", 66.66, 80.0),
            ("Punarvasu", 80.0, 93.33),
            ("Pushya", 93.33, 106.66),
            ("Ashlesha", 106.66, 120.0),
            ("Magha", 120.0, 133.33),
            ("Purva Phalguni", 133.33, 146.66),
            ("Uttara Phalguni", 146.66, 160.0),
            ("Hasta", 160.0, 173.33),
            ("Chitra", 173.33, 186.66),
            ("Swati", 186.66, 200.0),
            ("Vishakha", 200.0, 213.33),
            ("Anuradha", 213.33, 226.66),
            ("Jyeshtha", 226.66, 240.0),
            ("Mula", 240.0, 253.33),
            ("Purva Ashadha", 253.33, 266.66),
            ("Uttara Ashadha", 266.66, 276.66),
            ("Abhijit", 276.66, 280.88),
            ("Shravana", 280.88, 293.33),
            ("Dhanishta", 293.33, 306.66),
            ("Shatabhisha", 306.66, 320.0),
            ("Purva Bhadrapada", 320.0, 333.33),
            ("Uttara Bhadrapada", 333.33, 346.66),
            ("Revati", 346.66, 360.0),
        ]

    def get_nakshatra_and_lord(self, degree: float) -> tuple[str, str]:
        for name, start, end in self.boundaries:
            if start <= degree < end:
                return name, self.dasa_map[name]
        return "Revati", "Jupiter"


def _compute_obi(q_bid: float, q_ask: float) -> float:
    total = q_bid + q_ask
    if total <= 0:
        return 0.0
    return float((q_bid - q_ask) / total * 100.0)


class GodzillaProductionEngine:
    def __init__(
        self,
        symbol: str = "BTCUSDT",
        price_per_degree: float = 200.0,
        static_anchor: float = 16000.0,
        min_ppd: float = DEFAULT_MIN_PPD,
        max_ppd: float = DEFAULT_MAX_PPD,
        moon_velocity_5m: float = MOON_VELOCITY_5M,
    ) -> None:
        self.symbol = symbol.upper()
        self.fallback_ppd = price_per_degree
        self.ppd = price_per_degree
        self.ppd_cal: float | None = None
        self.static_anchor = static_anchor
        self.vector_map = AshtottariVectorMap()

        self.scaling_factor = GRID_SCALING_FACTOR
        self.min_ppd = min_ppd
        self.max_ppd = max_ppd
        self.moon_velocity_5m = moon_velocity_5m
        self.atr_period = DEFAULT_ATR_PERIOD
        self.ppd_meta: dict[str, Any] = {}

        self.account_balance = 1000.0
        self.risk_per_trade = 0.02
        self.leverage = 50
        self.maintenance_margin_rate = 0.005

        self.last_calibration_time: datetime | None = None
        self.last_anchor_candle_close: int | None = None
        self.anchor_lookback_interval = ANCHOR_INTERVAL
        self.anchor_lookback_limit = 72
        self.frozen_anchor: FrozenSwingAnchor | None = None

        self.active_trade: dict[str, Any] | None = None
        self.trade_history: list[dict[str, Any]] = []

        self._live_price: float = 0.0
        self._live_high: float = 0.0
        self._live_low: float = 0.0
        self._live_volume: float = 0.0
        self._current_atr: float | None = None
        self._atr_volume_baseline: float = 0.0
        self._best_bid: float = 0.0
        self._best_ask: float = 0.0
        self._bid_qty: float = 0.0
        self._ask_qty: float = 0.0
        self._depth_bids: list[tuple[float, float]] = []
        self._depth_asks: list[tuple[float, float]] = []
        self._spoof = SpoofDetector()
        self._klines_df: pd.DataFrame | None = None
        self._stream_lock = asyncio.Lock()
        self._calibration_lock = asyncio.Lock()

    def fetch_market_data(
        self,
        interval: str = "5m",
        limit: int = 20,
        atr_period: int | None = None,
    ) -> pd.DataFrame | None:
        period = atr_period if atr_period is not None else self.atr_period
        params = {"symbol": self.symbol, "interval": interval, "limit": limit}
        try:
            response = requests.get(BINANCE_FUTURES_KLINES, params=params, timeout=10)
            response.raise_for_status()
            df = pd.DataFrame(
                response.json(),
                columns=[
                    "open_time",
                    "open",
                    "high",
                    "low",
                    "close",
                    "volume",
                    "close_time",
                    "quote_volume",
                    "trades",
                    "tb_base",
                    "tb_quote",
                    "ignore",
                ],
            )
            df["timestamp"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
            for col in ["open", "high", "low", "close", "volume"]:
                df[col] = df[col].astype(float)

            df["prev_close"] = df["close"].shift(1)
            df["tr1"] = df["high"] - df["low"]
            df["tr2"] = (df["high"] - df["prev_close"]).abs()
            df["tr3"] = (df["low"] - df["prev_close"]).abs()
            df["true_range"] = df[["tr1", "tr2", "tr3"]].max(axis=1)
            df["atr"] = df["true_range"].rolling(window=period).mean()
            return df
        except Exception as exc:
            logger.error("Market data fetch failed: %s", exc)
            return None

    def calculate_celestial_coordinates(self, dt: datetime) -> dict[str, Any]:
        snap = celestial_snapshot(dt)
        moon_deg = snap["moon_degree"]
        mars_deg = snap["mars_degree"]
        mercury_deg = snap["mercury_degree"]

        aspect_diff = abs(moon_deg - mars_deg) % 360.0
        is_high_volume_aspect = any(
            abs(aspect_diff - target) < 3.0 or abs(aspect_diff - (360.0 - target)) < 3.0
            for target in (0.0, 90.0, 180.0)
        )

        confluence = analyze_confluence(moon_deg, mercury_deg, mars_deg)

        return {
            "moon_degree": float(moon_deg),
            "mars_degree": float(mars_deg),
            "mercury_degree": float(mercury_deg),
            "high_volume_aspect": is_high_volume_aspect,
            "moon_sign": degree_to_sign(moon_deg)["label"],
            "mars_sign": degree_to_sign(mars_deg)["label"],
            "mercury_sign": degree_to_sign(mercury_deg)["label"],
            "confluence": confluence,
        }

    def calculate_mw_vector_grid(
        self,
        moon_deg: float,
        current_atr: float | None = None,
    ) -> dict[str, Any]:
        cal_ppd = self.ppd_cal if self.ppd_cal is not None else self.ppd
        nakshatra, lord = self.vector_map.get_nakshatra_and_lord(moon_deg)
        linear_floor = self.static_anchor + (moon_deg * cal_ppd)
        extremes = lattice_extremes_from_primary(linear_floor, cal_ppd, current_atr)
        half_band = extremes["lattice_half_band"]
        harmonics = build_harmonic_nodes(linear_floor, half_band)

        return {
            "nakshatra_active": nakshatra,
            "dasa_lord": lord,
            "primary_vector_support": round(extremes["primary_vector_support"], 2),
            "upper_lattice_node": round(extremes["upper_lattice_node"], 2),
            "lower_lattice_node": round(extremes["lower_lattice_node"], 2),
            "lattice_half_band": round(extremes["lattice_half_band"], 2),
            "band_degrees": round(extremes["band_degrees"], 4),
            "harmonics": harmonics,
        }

    def update_dynamic_ppd(self, current_atr: float | None) -> float:
        """Recalculate live PPD from ATR — does NOT mutate frozen static anchor."""
        ppd, meta = calculate_dynamic_ppd(
            current_atr,
            moon_velocity_5m=self.moon_velocity_5m,
            scaling_factor=GRID_SCALING_FACTOR,
            min_ppd=self.min_ppd,
            max_ppd=self.max_ppd,
            fallback_ppd=self.fallback_ppd,
        )
        self.ppd = ppd
        self.ppd_meta = meta
        return ppd

    def _completed_candle_close_time(self, df: pd.DataFrame) -> int | None:
        if df is None or len(df) < 2:
            return None
        return int(df.iloc[-2]["close_time"])

    def should_recalibrate_anchor(self, df: pd.DataFrame) -> bool:
        if self.frozen_anchor is None:
            return True
        candle_close = self._completed_candle_close_time(df)
        if candle_close is None:
            return False
        return candle_close != self.last_anchor_candle_close

    def calibrate_anchor(
        self,
        df: pd.DataFrame | None = None,
        current_atr: float | None = None,
    ) -> None:
        if df is None:
            df = self.fetch_market_data(
                interval=self.anchor_lookback_interval,
                limit=self.anchor_lookback_limit,
            )
        if df is None or df.empty:
            logger.warning("Anchor calibration skipped: no market data.")
            return

        if current_atr is None and "atr" in df.columns and len(df) >= 2:
            atr_val = df["atr"].iloc[-2]
            if not pd.isna(atr_val):
                current_atr = float(atr_val)

        cal_ppd = self.update_dynamic_ppd(current_atr)

        self.frozen_anchor = build_frozen_swing_anchor(
            df,
            ppd=cal_ppd,
            anchor_lookback_interval=self.anchor_lookback_interval,
            current_atr=current_atr,
        )
        self.ppd_cal = float(self.frozen_anchor.ppd_cal)
        self.static_anchor = float(self.frozen_anchor.static_anchor)
        self.last_calibration_time = datetime.now(timezone.utc)
        self.last_anchor_candle_close = self._completed_candle_close_time(df)

        if df is not None and len(df) >= self.atr_period:
            vol_slice = df["volume"].iloc[-self.atr_period :]
            self._atr_volume_baseline = float(vol_slice.mean()) if len(vol_slice) else 0.0
            self._spoof.atr_volume_baseline = self._atr_volume_baseline

        logger.info(
            "Anchor frozen (5m): anchor_price=%.2f pivot=%s ppd_cal=%.2f A=%.2f",
            self.frozen_anchor.anchor_price,
            self.frozen_anchor.pivot_type,
            self.ppd_cal,
            self.static_anchor,
        )

    async def refresh_calibration_if_needed(self) -> None:
        async with self._calibration_lock:
            df = self.fetch_market_data(
                interval="5m",
                limit=max(20, self.anchor_lookback_limit),
            )
            if df is None or df.empty:
                return
            self._klines_df = df
            atr_val = df["atr"].iloc[-2] if len(df) >= 2 else None
            current_atr = float(atr_val) if atr_val is not None and not pd.isna(atr_val) else None
            self._current_atr = current_atr
            self.update_dynamic_ppd(current_atr)

            if self.should_recalibrate_anchor(df):
                anchor_df = self.fetch_market_data(
                    interval=self.anchor_lookback_interval,
                    limit=self.anchor_lookback_limit,
                )
                self.calibrate_anchor(anchor_df if anchor_df is not None else df, current_atr)
            elif self.frozen_anchor is None:
                self.calibrate_anchor(df, current_atr)

    def _orderbook_metrics(self) -> dict[str, float]:
        q_bid = sum(q for _, q in self._depth_bids[:10]) if self._depth_bids else self._bid_qty
        q_ask = sum(q for _, q in self._depth_asks[:10]) if self._depth_asks else self._ask_qty

        spoof_bid = self._spoof.spoofed_volume_bid()
        spoof_ask = self._spoof.spoofed_volume_ask()
        q_bid_f = max(0.0, q_bid - spoof_bid)
        q_ask_f = max(0.0, q_ask - spoof_ask)

        spread = float(self._best_ask - self._best_bid) if self._best_ask and self._best_bid else 0.0
        return {
            "best_bid": float(self._best_bid),
            "best_ask": float(self._best_ask),
            "spread": round(spread, 4),
            "obi_pct": round(_compute_obi(q_bid, q_ask), 4),
            "filtered_obi_pct": round(_compute_obi(q_bid_f, q_ask_f), 4),
            "bid_qty": round(float(q_bid), 4),
            "ask_qty": round(float(q_ask), 4),
        }

    def build_telemetry_frame(self, timestamp_ms: int | None = None) -> dict[str, Any]:
        now_ms = timestamp_ms or int(datetime.now(timezone.utc).timestamp() * 1000)
        current_dt = datetime.fromtimestamp(now_ms / 1000.0, tz=timezone.utc)

        live_price = float(self._live_price)
        current_atr = self._current_atr
        reversal_tol = (
            float(current_atr * REVERSAL_ATR_FRACTION)
            if current_atr and not pd.isna(current_atr)
            else live_price * 0.0015
        )

        celestial = self.calculate_celestial_coordinates(current_dt)
        moon_deg = celestial["moon_degree"]
        grid = self.calculate_mw_vector_grid(moon_deg, current_atr)

        frozen = self.frozen_anchor
        anchor_payload: dict[str, Any] | None = None
        mw_structure: dict[str, Any] | None = None
        anchor_warnings: list[str] = []

        if frozen is not None:
            anchor_dict = frozen.to_dict()
            anchor_payload = {
                **anchor_dict,
                "live_price": round(live_price, 2),
                "swing_anchor_price": round(frozen.sun_anchor_price, 2),
                "anchor_interval": ANCHOR_INTERVAL,
            }
            mw_structure = {
                "vertices": build_mw_vertices(frozen, ppd=self.ppd, current_atr=current_atr),
                "entry_degree": frozen.moon_degree_at_pivot,
                "exit_degree": frozen.sun_degree_at_pivot,
            }
            anchor_warnings = validate_anchor_prices(frozen, live_price)

        self.manage_active_positions(
            live_price,
            current_dt,
            float(self._live_high or live_price),
            float(self._live_low or live_price),
        )

        dist_to_primary = abs(live_price - grid["primary_vector_support"])
        dist_to_upper = abs(live_price - grid["upper_lattice_node"])

        all_harmonics = grid.get("harmonics", {}).get("upper", []) + grid.get("harmonics", {}).get("lower", [])
        near_harmonic = any(abs(live_price - float(h["price"])) <= reversal_tol for h in all_harmonics)

        signal_status = "IN_TRADE" if self.active_trade else "SCANNING"
        signal_message = "Monitoring MW lattice nodes for confluence."
        high_vol_window = celestial["high_volume_aspect"]

        if not self.active_trade and high_vol_window:
            risk_amount = self.account_balance * self.risk_per_trade
            if dist_to_primary < reversal_tol:
                sl_price = live_price - float(current_atr or live_price * 0.002)
                position_size = risk_amount / abs(live_price - sl_price)
                liq_price = live_price * (1 - (1 / self.leverage) + self.maintenance_margin_rate)
                effective_sl = max(sl_price, liq_price)
                signal_status = "LONG_CONFLUENCE"
                signal_message = "MW grid collapse: LONG confluence confirmed at primary vector."
                self.active_trade = {
                    "entry_time": current_dt,
                    "bias": "LONG",
                    "entry": live_price,
                    "leverage": self.leverage,
                    "position_size": position_size,
                    "sl": sl_price,
                    "liq_price": liq_price,
                    "effective_sl": effective_sl,
                    "tp": live_price + (float(current_atr or live_price * 0.002) * 2),
                    "status": "OPEN",
                }
            elif dist_to_upper < reversal_tol:
                sl_price = live_price + float(current_atr or live_price * 0.002)
                position_size = risk_amount / abs(sl_price - live_price)
                liq_price = live_price * (1 + (1 / self.leverage) - self.maintenance_margin_rate)
                effective_sl = min(sl_price, liq_price)
                signal_status = "SHORT_CONFLUENCE"
                signal_message = "MW grid collapse: SHORT confluence confirmed at upper lattice."
                self.active_trade = {
                    "entry_time": current_dt,
                    "bias": "SHORT",
                    "entry": live_price,
                    "leverage": self.leverage,
                    "position_size": position_size,
                    "sl": sl_price,
                    "liq_price": liq_price,
                    "effective_sl": effective_sl,
                    "tp": live_price - (float(current_atr or live_price * 0.002) * 2),
                    "status": "OPEN",
                }
        elif not high_vol_window and not self.active_trade:
            signal_message = "No high-volume Moon–Mars aspect window active."

        ob = self._orderbook_metrics()
        vortex = vortex_flags(live_price, now_ms, self._live_volume)
        atr_safe = float(current_atr) if current_atr and not pd.isna(current_atr) else 1.0
        norm_x = (live_price - grid["primary_vector_support"]) / atr_safe if atr_safe > 0 else 0.0

        return {
            "symbol": self.symbol,
            "timestamp": current_dt.isoformat(),
            "timestamp_ms": now_ms,
            "market": {
                "live_price": round(live_price, 2),
                "price": round(live_price, 2),
                "high": round(float(self._live_high or live_price), 2),
                "low": round(float(self._live_low or live_price), 2),
                "atr": round(float(current_atr), 2) if current_atr and not pd.isna(current_atr) else None,
                "atr_tolerance": round(reversal_tol, 2),
                "volume": round(float(self._live_volume), 4),
                "spread": ob["spread"],
                "best_bid": ob["best_bid"],
                "best_ask": ob["best_ask"],
                "obi_pct": ob["obi_pct"],
                "filtered_obi_pct": ob["filtered_obi_pct"],
                "bid_qty": ob["bid_qty"],
                "ask_qty": ob["ask_qty"],
                "normalized_x": round(norm_x, 6),
            },
            "vortex": vortex,
            "spoof_alerts": self._spoof.active_alerts(),
            "anchor": anchor_payload,
            "mw_structure": mw_structure,
            "anchor_validation": anchor_warnings,
            "celestial": {
                "moon_degree": round(moon_deg, 2),
                "mars_degree": round(celestial["mars_degree"], 2),
                "mercury_degree": round(celestial["mercury_degree"], 2),
                "high_volume_aspect": high_vol_window,
                "moon_sign": celestial["moon_sign"],
                "mars_sign": celestial["mars_sign"],
                "mercury_sign": celestial["mercury_sign"],
                "confluence": celestial["confluence"],
            },
            "grid": {
                **grid,
                "price_per_degree": self.ppd,
                "ppd_cal": self.ppd_cal,
                "static_anchor": round(self.static_anchor, 2),
                "fallback_ppd": self.fallback_ppd,
                "dynamic_ppd": self.ppd,
                "ppd_source": self.ppd_meta.get("source", "fallback"),
                "scaling_factor": GRID_SCALING_FACTOR,
                "ppd_meta": self.ppd_meta,
                "atr_period": self.atr_period,
                "swing_anchor_price": (
                    round(frozen.sun_anchor_price, 2) if frozen is not None else None
                ),
                "moon_degree_at_pivot": (
                    round(frozen.moon_degree_at_pivot, 2) if frozen is not None else None
                ),
                "pivot_type": frozen.pivot_type if frozen is not None else None,
                "last_calibration": (
                    self.last_calibration_time.isoformat() if self.last_calibration_time else None
                ),
                "last_anchor_candle_close": self.last_anchor_candle_close,
                "anchor_interval": self.anchor_lookback_interval,
                "near_harmonic": near_harmonic,
                **lattice_extremes_meta(self.ppd_cal or self.ppd, current_atr),
            },
            "distances": {
                "to_primary": round(dist_to_primary, 2),
                "to_upper": round(dist_to_upper, 2),
            },
            "signal": {
                "status": signal_status,
                "message": signal_message,
            },
            "active_trade": (
                self._serialize_trade(self.active_trade) if self.active_trade else None
            ),
            "account": {
                "balance": round(self.account_balance, 2),
                "leverage": self.leverage,
                "risk_per_trade_pct": round(self.risk_per_trade * 100, 2),
            },
            "trade_history": list(reversed(self.trade_history[-10:])),
        }

    def run_matrix_scanner(self) -> dict[str, Any]:
        """Synchronous one-shot scan (legacy REST path)."""
        df_5m = self.fetch_market_data(
            interval="5m",
            limit=max(20, self.anchor_lookback_limit),
        )
        if df_5m is None or df_5m.empty:
            raise RuntimeError("Unable to fetch market data from Binance.")

        live_5m = df_5m.iloc[-1]
        self._live_price = float(live_5m["close"])
        self._live_high = float(live_5m["high"])
        self._live_low = float(live_5m["low"])
        self._live_volume = float(live_5m["volume"])
        current_atr = df_5m["atr"].iloc[-2]
        self._current_atr = float(current_atr) if not pd.isna(current_atr) else None
        self.update_dynamic_ppd(self._current_atr)

        if self.should_recalibrate_anchor(df_5m):
            anchor_df = self.fetch_market_data(
                interval=self.anchor_lookback_interval,
                limit=self.anchor_lookback_limit,
            )
            self.calibrate_anchor(anchor_df if anchor_df is not None else df_5m, self._current_atr)
        elif self.frozen_anchor is None:
            self.calibrate_anchor(df_5m, self._current_atr)

        ts_ms = int(live_5m["close_time"]) if "close_time" in live_5m else None
        return self.build_telemetry_frame(ts_ms)

    def _binance_stream_url(self) -> str:
        sym = self.symbol.lower()
        streams = "/".join(
            [
                f"{sym}@depth20@100ms",
                f"{sym}@aggTrade",
                f"{sym}@bookTicker",
            ]
        )
        return f"{BINANCE_FUTURES_WS}?streams={streams}"

    def _handle_depth(self, payload: dict[str, Any]) -> None:
        bids = [(float(p), float(q)) for p, q in payload.get("b", [])[:10]]
        asks = [(float(p), float(q)) for p, q in payload.get("a", [])[:10]]
        self._depth_bids = bids
        self._depth_asks = asks
        if bids:
            self._best_bid = bids[0][0]
            self._bid_qty = bids[0][1]
        if asks:
            self._best_ask = asks[0][0]
            self._ask_qty = asks[0][1]
        ts = int(payload.get("E") or payload.get("T") or 0)
        self._spoof.update_depth(bids, asks, ts)

    def _handle_agg_trade(self, payload: dict[str, Any]) -> None:
        price = float(payload.get("p", 0))
        qty = float(payload.get("q", 0))
        ts = int(payload.get("T") or payload.get("E") or 0)
        self._live_price = price
        self._live_volume = qty
        self._spoof.record_trade(price, qty, ts)

    def _handle_book_ticker(self, payload: dict[str, Any]) -> None:
        self._best_bid = float(payload.get("b", 0))
        self._best_ask = float(payload.get("a", 0))
        self._bid_qty = float(payload.get("B", 0))
        self._ask_qty = float(payload.get("A", 0))

    async def run_live_stream(
        self,
        on_frame: Callable[[dict[str, Any]], Awaitable[None]],
        *,
        calibration_interval: float = 30.0,
    ) -> None:
        """Stream unified telemetry from Binance futures depth + aggTrade + bookTicker."""
        await self.refresh_calibration_if_needed()
        last_cal = asyncio.get_event_loop().time()

        while True:
            try:
                url = self._binance_stream_url()
                logger.info("Connecting Binance live stream: %s", self.symbol)
                async with websockets.connect(url, ping_interval=20, ping_timeout=20) as ws:
                    while True:
                        now_loop = asyncio.get_event_loop().time()
                        if now_loop - last_cal >= calibration_interval:
                            await self.refresh_calibration_if_needed()
                            last_cal = now_loop

                        raw = await ws.recv()
                        envelope = json.loads(raw)
                        stream = envelope.get("stream", "")
                        data = envelope.get("data", envelope)

                        if "@depth" in stream:
                            self._handle_depth(data)
                        elif "@aggTrade" in stream:
                            self._handle_agg_trade(data)
                        elif "@bookTicker" in stream:
                            self._handle_book_ticker(data)

                        ts_ms = int(
                            data.get("T") or data.get("E") or datetime.now(timezone.utc).timestamp() * 1000
                        )
                        frame = self.build_telemetry_frame(ts_ms)
                        await on_frame({"event": "matrix_frame", "data": frame})

            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error("Live stream error (%s): %s — reconnecting", self.symbol, exc)
                await asyncio.sleep(3)

    def _serialize_trade(self, trade: dict[str, Any]) -> dict[str, Any]:
        serialized = dict(trade)
        for key in ("entry_time", "exit_time"):
            if key in serialized and serialized[key] is not None:
                value = serialized[key]
                if hasattr(value, "isoformat"):
                    serialized[key] = value.isoformat()
                else:
                    serialized[key] = str(value)
        for key in (
            "entry",
            "exit_price",
            "sl",
            "tp",
            "liq_price",
            "effective_sl",
            "position_size",
            "pnl_amount",
        ):
            if key in serialized and serialized[key] is not None:
                serialized[key] = round(float(serialized[key]), 4)
        return serialized

    def close_position(self, current_price: float, current_time: datetime, reason: str) -> None:
        if not self.active_trade:
            return

        trade = self.active_trade
        trade["exit_time"] = current_time
        trade["exit_price"] = current_price
        trade["status"] = reason

        entry, exit_px = trade["entry"], current_price
        if trade["bias"] == "LONG":
            pnl_amount = trade["position_size"] * (exit_px - entry)
        else:
            pnl_amount = trade["position_size"] * (entry - exit_px)

        trade["pnl_amount"] = round(pnl_amount, 2)
        trade["pnl_pct_of_balance"] = round((pnl_amount / self.account_balance) * 100, 2)
        self.account_balance += pnl_amount
        self.trade_history.append(self._serialize_trade(trade))
        self.active_trade = None

    def manage_active_positions(
        self,
        current_price: float,
        current_time: datetime,
        high_price: float,
        low_price: float,
    ) -> None:
        if not self.active_trade:
            return

        trade = self.active_trade
        entry_time = trade["entry_time"]
        if hasattr(entry_time, "to_pydatetime"):
            entry_time = entry_time.to_pydatetime()

        if current_time - entry_time >= timedelta(hours=24):
            self.close_position(current_price, current_time, "EXPIRED_24H")
            return

        if trade["bias"] == "LONG":
            if low_price <= trade["effective_sl"]:
                reason = "LIQUIDATED" if trade["liq_price"] >= trade["sl"] else "STOP_LOSS"
                self.close_position(trade["effective_sl"], current_time, reason)
            elif high_price >= trade["tp"]:
                self.close_position(trade["tp"], current_time, "TAKE_PROFIT")
        elif trade["bias"] == "SHORT":
            if high_price >= trade["effective_sl"]:
                reason = "LIQUIDATED" if trade["liq_price"] <= trade["sl"] else "STOP_LOSS"
                self.close_position(trade["effective_sl"], current_time, reason)
            elif low_price <= trade["tp"]:
                self.close_position(trade["tp"], current_time, "TAKE_PROFIT")


_engines: dict[str, GodzillaProductionEngine] = {}


def get_engine(
    symbol: str = "BTCUSDT",
    price_per_degree: float = 200.0,
    leverage: int = 50,
) -> GodzillaProductionEngine:
    key = f"{symbol.upper()}:{price_per_degree}:{leverage}"
    if key not in _engines:
        engine = GodzillaProductionEngine(symbol=symbol, price_per_degree=price_per_degree)
        engine.leverage = leverage
        _engines[key] = engine
    return _engines[key]
