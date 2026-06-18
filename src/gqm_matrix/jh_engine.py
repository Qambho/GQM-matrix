from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from gqm_matrix.market import BinanceMarketClient


class GqmMatrixJHEngineV72:
    def __init__(
        self,
        base_asset: str = "BTCUSDT",
        leverage: int = 50,
        data_dir: str | Path | None = None,
        market_client: BinanceMarketClient | None = None,
    ) -> None:
        self.base_asset = base_asset.upper()
        self.leverage = leverage
        self.data_dir = Path(data_dir) if data_dir else Path(__file__).resolve().parents[2] / "data"
        self.market_client = market_client or BinanceMarketClient()

        self.STEP_FACTOR = 1.43
        self.GRID_CONSTANT = 13.79
        self.LEVERAGE_FACTOR = 0.75
        self.VECTOR_SWITCH = 1.59
        self.MATRIX_ALPHA_ANCHOR = 273

        self.VALID_PLANETS = [
            "Sun",
            "Moon",
            "Mars",
            "Mercury",
            "Jupiter",
            "Venus",
            "Saturn",
            "Rahu",
            "Ketu",
        ]
        self.BULLISH_ANTARDASA = ["Rahu", "Jupiter", "Mercury", "Venus"]
        self.BEARISH_ANTARDASA = ["Saturn", "Ketu", "Sun", "Mars"]

        self.JH_MAP = {
            "Sun": "Su",
            "Moon": "Mo",
            "Mars": "Ma",
            "Mercury": "Me",
            "Jupiter": "Ju",
            "Venus": "Ve",
            "Saturn": "Sa",
            "Rahu": "Ra",
            "Ketu": "Ke",
        }

        self.active_ad: str | None = None
        self.signified_houses: list[int] = []
        self.kp_signifies_gain = False
        self.upcoming_good_windows: list[str] = []

        self.scan_parse_and_forecast()

    def scan_parse_and_forecast(self) -> None:
        dasa_path = self.data_dir / "dasas.txt"
        kp_path = self.data_dir / "kp.txt"

        dasa_content = dasa_path.read_text(encoding="utf-8")
        found_active = False

        for line in dasa_content.splitlines():
            clean_line = line.lower()

            if not found_active:
                if (
                    any(key in clean_line for key in ["anter", "antardasa", "ad:", "antardash"])
                    or (
                        "-" in clean_line
                        and any(planet.lower() in clean_line for planet in self.VALID_PLANETS)
                    )
                ):
                    for planet in self.VALID_PLANETS:
                        if planet.lower() in clean_line:
                            self.active_ad = planet
                            found_active = True
                            break
                    continue

            if found_active:
                for planet in self.VALID_PLANETS:
                    if planet.lower() in clean_line and planet in self.BULLISH_ANTARDASA:
                        self.upcoming_good_windows.append(line.strip())
                        break

        if not self.active_ad:
            raise ValueError("Could not automatically isolate the active Antardasa layer from file.")

        target_abbrev = self.JH_MAP.get(self.active_ad)
        if not target_abbrev:
            raise ValueError(f"Could not map translation shorthand for planet: {self.active_ad}")

        kp_content = kp_path.read_text(encoding="utf-8")
        self.signified_houses = []

        for line in kp_content.splitlines():
            clean_line = line.strip()
            if "house" not in clean_line.lower():
                continue

            parts = clean_line.split()
            if len(parts) < 4:
                continue

            house_match = re.search(r"\d+", parts[0])
            if not house_match:
                continue

            house_num = int(house_match.group())
            nakshatra_lord = parts[2]
            sub_lord = parts[3]

            if nakshatra_lord == target_abbrev or sub_lord == target_abbrev:
                if house_num not in self.signified_houses:
                    self.signified_houses.append(house_num)

        self.signified_houses.sort()

        gain_score = sum(1 for house in self.signified_houses if house in [2, 6, 11])
        loss_score = sum(1 for house in self.signified_houses if house in [8, 12])
        self.kp_signifies_gain = gain_score > loss_score and gain_score > 0

    def get_public_market_index(self) -> float | None:
        try:
            return self.market_client.get_price(self.base_asset)
        except Exception:
            return None

    def calculate_date_root(self) -> int:
        now = datetime.now(timezone.utc)
        date_root = sum(int(digit) for digit in str(now.day))
        while date_root > 9:
            date_root = sum(int(digit) for digit in str(date_root))
        return date_root

    def apply_273_multiplier_logic(self, current_price: float, base_band: float, bias: str) -> float:
        scaled_multiplier = self.MATRIX_ALPHA_ANCHOR / 100
        if bias == "LONG":
            extended_target = current_price + (base_band * scaled_multiplier)
        else:
            extended_target = current_price - (base_band * scaled_multiplier)
        return round(extended_target, 2)

    def generate_astro_matrix(self, current_price: float) -> dict[str, float | int | str]:
        date_root = self.calculate_date_root()
        speed_multiplier = self.STEP_FACTOR * self.GRID_CONSTANT
        base_band = current_price * (speed_multiplier / 1000)
        risk_offset = base_band * ((self.LEVERAGE_FACTOR * self.leverage) / 100)

        base_bias = "LONG" if date_root in [3, 5, 6, 9] else "SHORT"

        if self.active_ad in self.BULLISH_ANTARDASA and base_bias == "SHORT":
            bias = "LONG"
        elif self.active_ad in self.BEARISH_ANTARDASA and base_bias == "LONG":
            bias = "SHORT"
        else:
            bias = base_bias

        if bias == "LONG":
            entry_zone = current_price - (base_band * 0.05)
            standard_target = current_price + (base_band * self.VECTOR_SWITCH)
            stop_loss = current_price - risk_offset
        else:
            entry_zone = current_price + (base_band * 0.05)
            standard_target = current_price - (base_band * self.VECTOR_SWITCH)
            stop_loss = current_price + risk_offset

        network_node_target = self.apply_273_multiplier_logic(current_price, base_band, bias)

        return {
            "date_root": date_root,
            "bias": bias,
            "base_band": round(base_band, 2),
            "entry_zone": round(entry_zone, 2),
            "standard_target": round(standard_target, 2),
            "network_node_target": network_node_target,
            "stop_loss": round(stop_loss, 2),
        }

    def generate_blueprint_report(self) -> dict[str, object]:
        current_price = self.get_public_market_index()
        if current_price is None:
            raise RuntimeError("Public price stream unavailable from Binance Futures API.")

        matrix = self.generate_astro_matrix(current_price)
        market_ticker = self.market_client.get_24h_ticker(self.base_asset)

        return {
            "asset": self.base_asset,
            "leverage": self.leverage,
            "market": market_ticker,
            "market_source": "Binance USD-M Futures (public)",
            "current_price": current_price,
            "active_antardasa": self.active_ad,
            "active_antardasa_abbrev": self.JH_MAP.get(self.active_ad),
            "signified_houses": self.signified_houses,
            "kp_signifies_gain": self.kp_signifies_gain,
            "upcoming_good_windows": self.upcoming_good_windows[:3],
            "matrix": matrix,
            "notice": (
                "Astro-KP confirmation values aligned with current matrix direction."
                if self.kp_signifies_gain
                else "KP Filter active and flagged unfavorable house balance."
            ),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
