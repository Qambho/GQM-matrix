"""Godzilla V4 MW Advanced Vector Engine — Ashtottari lattice matrix scanner."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import ephem
import numpy as np
import pandas as pd
import requests

from gqm_matrix.celestial_aspects import analyze_confluence, degree_to_sign
from gqm_matrix.dynamic_ppd import (
    DEFAULT_ATR_PERIOD,
    DEFAULT_MAX_PPD,
    DEFAULT_MIN_PPD,
    DEFAULT_SCALING_FACTOR,
    MOON_VELOCITY_5M,
    calculate_dynamic_ppd,
)
from gqm_matrix.mw_anchor import (
    FrozenSwingAnchor,
    build_frozen_swing_anchor,
    build_mw_vertices,
    validate_anchor_prices,
)

logger = logging.getLogger("GodzillaEngine")

BINANCE_FUTURES_KLINES = "https://fapi.binance.com/fapi/v1/klines"


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


class GodzillaProductionEngine:
    def __init__(
        self,
        symbol: str = "BTCUSDT",
        price_per_degree: float = 200.0,
        static_anchor: float = 16000.0,
        scaling_factor: float = DEFAULT_SCALING_FACTOR,
        min_ppd: float = DEFAULT_MIN_PPD,
        max_ppd: float = DEFAULT_MAX_PPD,
        moon_velocity_5m: float = MOON_VELOCITY_5M,
    ) -> None:
        self.symbol = symbol.upper()
        self.fallback_ppd = price_per_degree
        self.ppd = price_per_degree
        self.static_anchor = static_anchor
        self.ayanamsha = 24.2
        self.vector_map = AshtottariVectorMap()

        self.scaling_factor = scaling_factor
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
        self.anchor_lookback_interval = "5m"
        self.anchor_lookback_limit = 72
        self.frozen_anchor: FrozenSwingAnchor | None = None

        self.active_trade: dict[str, Any] | None = None
        self.trade_history: list[dict[str, Any]] = []

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
        utc_dt = dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)
        ephem_date = utc_dt.strftime("%Y/%m/%d %H:%M:%S")

        moon = ephem.Moon()
        moon.compute(ephem_date)
        moon_deg = (np.degrees(ephem.Ecliptic(moon).lon) - self.ayanamsha) % 360.0

        mars = ephem.Mars()
        mars.compute(ephem_date)
        mars_deg = (np.degrees(ephem.Ecliptic(mars).lon) - self.ayanamsha) % 360.0

        mercury = ephem.Mercury()
        mercury.compute(ephem_date)
        mercury_deg = (np.degrees(ephem.Ecliptic(mercury).lon) - self.ayanamsha) % 360.0

        aspect_diff = abs(moon_deg - mars_deg) % 360.0
        is_high_volume_aspect = any(
            abs(aspect_diff - target) < 3.0 or abs(aspect_diff - (360.0 - target)) < 3.0
            for target in (0.0, 90.0, 180.0)
        )

        confluence = analyze_confluence(moon_deg, mercury_deg, mars_deg)
        moon_sign = degree_to_sign(moon_deg)
        mars_sign = degree_to_sign(mars_deg)
        mercury_sign = degree_to_sign(mercury_deg)

        return {
            "moon_degree": float(moon_deg),
            "mars_degree": float(mars_deg),
            "mercury_degree": float(mercury_deg),
            "high_volume_aspect": is_high_volume_aspect,
            "moon_sign": moon_sign["label"],
            "mars_sign": mars_sign["label"],
            "mercury_sign": mercury_sign["label"],
            "confluence": confluence,
        }

    def calculate_mw_vector_grid(self, moon_deg: float) -> dict[str, Any]:
        nakshatra, lord = self.vector_map.get_nakshatra_and_lord(moon_deg)
        linear_floor = self.static_anchor + (moon_deg * self.ppd)
        return {
            "nakshatra_active": nakshatra,
            "dasa_lord": lord,
            "primary_vector_support": round(linear_floor, 2),
            "upper_lattice_node": round(linear_floor + (13.33 * self.ppd), 2),
            "lower_lattice_node": round(linear_floor - (13.33 * self.ppd), 2),
        }

    def update_dynamic_ppd(self, current_atr: float | None) -> float:
        """Recalculate lattice sensitivity from 5-period ATR and Moon velocity."""
        ppd, meta = calculate_dynamic_ppd(
            current_atr,
            moon_velocity_5m=self.moon_velocity_5m,
            scaling_factor=self.scaling_factor,
            min_ppd=self.min_ppd,
            max_ppd=self.max_ppd,
            fallback_ppd=self.fallback_ppd,
        )
        self.ppd = ppd
        self.ppd_meta = meta
        if self.frozen_anchor is not None:
            moon = self.frozen_anchor.moon_degree_at_pivot
            self.static_anchor = self.frozen_anchor.anchor_price - (moon * ppd)
        return ppd

    def _completed_candle_close_time(self, df: pd.DataFrame) -> int | None:
        """Binance close_time (ms) of the last fully closed candle."""
        if df is None or len(df) < 2:
            return None
        return int(df.iloc[-2]["close_time"])

    def should_recalibrate_anchor(self, df: pd.DataFrame) -> bool:
        """True when a new 5m candle has closed since the last anchor calibration."""
        if self.frozen_anchor is None:
            return True
        candle_close = self._completed_candle_close_time(df)
        if candle_close is None:
            return False
        return candle_close != self.last_anchor_candle_close

    def calibrate_anchor(self, df: pd.DataFrame | None = None) -> None:
        if df is None:
            df = self.fetch_market_data(
                interval=self.anchor_lookback_interval,
                limit=self.anchor_lookback_limit,
            )
        if df is None or df.empty:
            logger.warning("Anchor calibration skipped: no market data.")
            return

        self.frozen_anchor = build_frozen_swing_anchor(
            df,
            ppd=self.ppd,
            ayanamsha=self.ayanamsha,
            anchor_lookback_interval=self.anchor_lookback_interval,
        )
        self.static_anchor = self.frozen_anchor.static_anchor
        self.last_calibration_time = datetime.now(timezone.utc)
        self.last_anchor_candle_close = self._completed_candle_close_time(df)
        logger.info(
            "Anchor frozen (5m): anchor_price=%.2f pivot=%s ppd=%.2f candle_close=%s",
            self.frozen_anchor.anchor_price,
            self.frozen_anchor.pivot_type,
            self.ppd,
            self.last_anchor_candle_close,
        )

    def _serialize_trade(self, trade: dict[str, Any]) -> dict[str, Any]:
        serialized = dict(trade)
        for key in ("entry_time", "exit_time"):
            if key in serialized and serialized[key] is not None:
                value = serialized[key]
                if hasattr(value, "isoformat"):
                    serialized[key] = value.isoformat()
                else:
                    serialized[key] = str(value)
        for key in ("entry", "exit_price", "sl", "tp", "liq_price", "effective_sl", "position_size", "pnl_amount"):
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

    def run_matrix_scanner(self) -> dict[str, Any]:
        df_5m = self.fetch_market_data(
            interval="5m",
            limit=max(20, self.anchor_lookback_limit),
        )
        if df_5m is None or df_5m.empty:
            raise RuntimeError("Unable to fetch market data from Binance.")

        live_5m = df_5m.iloc[-1]
        live_price = float(live_5m["close"])
        current_time = live_5m["timestamp"]
        current_dt = current_time.to_pydatetime() if hasattr(current_time, "to_pydatetime") else current_time
        current_atr = df_5m["atr"].iloc[-2]

        self.update_dynamic_ppd(float(current_atr) if not pd.isna(current_atr) else None)

        if self.should_recalibrate_anchor(df_5m):
            anchor_df = self.fetch_market_data(
                interval=self.anchor_lookback_interval,
                limit=self.anchor_lookback_limit,
            )
            self.calibrate_anchor(anchor_df if anchor_df is not None else df_5m)
        elif self.frozen_anchor is None:
            self.calibrate_anchor(df_5m)

        dynamic_wick_tolerance = (
            float(current_atr * 0.5) if not pd.isna(current_atr) else live_price * 0.0015
        )

        celestial = self.calculate_celestial_coordinates(current_dt)
        moon_deg = celestial["moon_degree"]
        mars_deg = celestial["mars_degree"]
        mercury_deg = celestial["mercury_degree"]
        high_vol_window = celestial["high_volume_aspect"]
        confluence = celestial["confluence"]
        grid = self.calculate_mw_vector_grid(moon_deg)

        frozen = self.frozen_anchor
        anchor_payload: dict[str, Any] | None = None
        mw_structure: dict[str, Any] | None = None
        anchor_warnings: list[str] = []

        if frozen is not None:
            anchor_payload = {
                **frozen.to_dict(),
                "live_price": round(live_price, 2),
            }
            mw_structure = {
                "vertices": build_mw_vertices(frozen, ppd=self.ppd),
                "entry_degree": frozen.moon_degree_at_pivot,
                "exit_degree": frozen.sun_degree_at_pivot,
            }
            anchor_warnings = validate_anchor_prices(frozen, live_price)
            if anchor_warnings:
                for warning in anchor_warnings:
                    logger.warning("MW anchor validation: %s", warning)

        self.manage_active_positions(
            live_price,
            current_dt,
            float(live_5m["high"]),
            float(live_5m["low"]),
        )

        dist_to_primary = abs(live_price - grid["primary_vector_support"])
        dist_to_upper = abs(live_price - grid["upper_lattice_node"])

        signal_status = "IN_TRADE" if self.active_trade else "SCANNING"
        signal_message = "Monitoring MW lattice nodes for confluence."

        if not self.active_trade and high_vol_window:
            risk_amount = self.account_balance * self.risk_per_trade

            if dist_to_primary < dynamic_wick_tolerance:
                sl_price = live_price - float(current_atr)
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
                    "tp": live_price + (float(current_atr) * 2),
                    "status": "OPEN",
                }

            elif dist_to_upper < dynamic_wick_tolerance:
                sl_price = live_price + float(current_atr)
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
                    "tp": live_price - (float(current_atr) * 2),
                    "status": "OPEN",
                }
        elif not high_vol_window and not self.active_trade:
            signal_message = "No high-volume Moon–Mars aspect window active."

        return {
            "symbol": self.symbol,
            "timestamp": current_dt.isoformat(),
            "market": {
                "live_price": round(live_price, 2),
                "price": round(live_price, 2),
                "high": round(float(live_5m["high"]), 2),
                "low": round(float(live_5m["low"]), 2),
                "atr": round(float(current_atr), 2) if not pd.isna(current_atr) else None,
                "atr_tolerance": round(dynamic_wick_tolerance, 2),
            },
            "anchor": anchor_payload,
            "mw_structure": mw_structure,
            "anchor_validation": anchor_warnings,
            "celestial": {
                "moon_degree": round(moon_deg, 2),
                "mars_degree": round(mars_deg, 2),
                "mercury_degree": round(mercury_deg, 2),
                "high_volume_aspect": high_vol_window,
                "moon_sign": celestial["moon_sign"],
                "mars_sign": celestial["mars_sign"],
                "mercury_sign": celestial["mercury_sign"],
                "confluence": confluence,
            },
            "grid": {
                **grid,
                "price_per_degree": self.ppd,
                "fallback_ppd": self.fallback_ppd,
                "dynamic_ppd": self.ppd,
                "ppd_source": self.ppd_meta.get("source", "fallback"),
                "scaling_factor": self.scaling_factor,
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
