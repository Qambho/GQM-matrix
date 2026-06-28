"""Frozen swing-pivot anchor for the M-W lattice (decoupled from live spot)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import ephem
import numpy as np
import pandas as pd

from gqm_matrix.lattice_band import lattice_extremes_from_primary

logger = logging.getLogger("MWAnchor")

# Fractal bars each side for confirmed 5m swings
SWING_LEFT_BARS = 2
SWING_RIGHT_BARS = 2


@dataclass
class FrozenSwingAnchor:
    """Swing-based anchor frozen at calibration — must not use live spot."""

    anchor_price: float
    anchor_timestamp: datetime
    pivot_type: str
    static_anchor: float
    moon_degree_at_pivot: float
    sun_degree_at_pivot: float
    mars_degree_at_pivot: float
    primary_vector_support: float
    upper_lattice_node: float
    lower_lattice_node: float
    exit_upper_node: float
    sun_anchor_price: float
    lookback_high: float
    lookback_low: float
    anchor_lookback_interval: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "anchor_price": round(self.anchor_price, 2),
            "sun_anchor_price": round(self.sun_anchor_price, 2),
            "anchor_timestamp": self.anchor_timestamp.isoformat(),
            "pivot_type": self.pivot_type,
            "static_anchor": round(self.static_anchor, 2),
            "moon_degree_at_pivot": round(self.moon_degree_at_pivot, 2),
            "sun_degree_at_pivot": round(self.sun_degree_at_pivot, 2),
            "mars_degree_at_pivot": round(self.mars_degree_at_pivot, 2),
            "primary_vector_support": round(self.primary_vector_support, 2),
            "upper_lattice_node": round(self.upper_lattice_node, 2),
            "lower_lattice_node": round(self.lower_lattice_node, 2),
            "exit_upper_node": round(self.exit_upper_node, 2),
            "sun_crossing_price": round(self.sun_anchor_price, 2),
            "lookback_high": round(self.lookback_high, 2),
            "lookback_low": round(self.lookback_low, 2),
            "anchor_lookback_interval": self.anchor_lookback_interval,
        }


def sidereal_longitude(body: ephem.Body, dt: datetime, ayanamsha: float) -> float:
    from datetime import timezone

    utc_dt = dt.astimezone(timezone.utc) if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    ephem_date = utc_dt.strftime("%Y/%m/%d %H:%M:%S")
    body.compute(ephem_date)
    return float((np.degrees(ephem.Ecliptic(body).lon) - ayanamsha) % 360.0)


def _to_dt(value: Any) -> datetime:
    if hasattr(value, "to_pydatetime"):
        return value.to_pydatetime()
    return value


def _is_swing_high(df: pd.DataFrame, i: int, left: int, right: int) -> bool:
    high = float(df.iloc[i]["high"])
    for j in range(1, left + 1):
        if high < float(df.iloc[i - j]["high"]):
            return False
    for j in range(1, right + 1):
        if high <= float(df.iloc[i + j]["high"]):
            return False
    return True


def _is_swing_low(df: pd.DataFrame, i: int, left: int, right: int) -> bool:
    low = float(df.iloc[i]["low"])
    for j in range(1, left + 1):
        if low > float(df.iloc[i - j]["low"]):
            return False
    for j in range(1, right + 1):
        if low >= float(df.iloc[i + j]["low"]):
            return False
    return True


def find_last_swings(
    df: pd.DataFrame,
    left: int = SWING_LEFT_BARS,
    right: int = SWING_RIGHT_BARS,
) -> tuple[tuple[float, datetime, int] | None, tuple[float, datetime, int] | None]:
    """Return the most recent confirmed swing high and swing low on the series."""
    last_high: tuple[float, datetime, int] | None = None
    last_low: tuple[float, datetime, int] | None = None
    n = len(df)

    if n < left + right + 1:
        return None, None

    for i in range(left, n - right):
        if _is_swing_high(df, i, left, right):
            last_high = (float(df.iloc[i]["high"]), _to_dt(df.iloc[i]["timestamp"]), i)
        if _is_swing_low(df, i, left, right):
            last_low = (float(df.iloc[i]["low"]), _to_dt(df.iloc[i]["timestamp"]), i)

    return last_high, last_low


# Backward-compatible alias
find_last_15m_swings = find_last_swings


def identify_last_swing_pivot(
    df: pd.DataFrame,
    interval_label: str = "5m",
) -> tuple[float, datetime, str, float, float]:
    """
    Sun anchor = price of the last confirmed swing high or swing low.
    Never uses CMP / last close as the anchor price.
    """
    lookback_high = float(df["high"].max())
    lookback_low = float(df["low"].min())
    last_close = float(df["close"].iloc[-1])

    last_high, last_low = find_last_swings(df)

    if last_high is None and last_low is None:
        logger.warning(
            "No fractal swings found on %s — falling back to window extrema (not CMP).",
            interval_label,
        )
        idx_high = df["high"].idxmax()
        idx_low = df["low"].idxmin()
        high_val = float(df.loc[idx_high, "high"])
        low_val = float(df.loc[idx_low, "low"])
        if abs(last_close - high_val) <= abs(last_close - low_val):
            pivot_time = df.loc[idx_low, "timestamp"]
            return low_val, _to_dt(pivot_time), "swing_low", lookback_high, lookback_low
        pivot_time = df.loc[idx_high, "timestamp"]
        return high_val, _to_dt(pivot_time), "swing_high", lookback_high, lookback_low

    if last_high is None:
        price, ts, _ = last_low
        return price, ts, "swing_low", lookback_high, lookback_low

    if last_low is None:
        price, ts, _ = last_high
        return price, ts, "swing_high", lookback_high, lookback_low

    high_price, high_ts, high_idx = last_high
    low_price, low_ts, low_idx = last_low

    if high_idx > low_idx:
        return high_price, high_ts, "swing_high", lookback_high, lookback_low
    return low_price, low_ts, "swing_low", lookback_high, lookback_low


def build_frozen_swing_anchor(
    df: pd.DataFrame,
    ppd: float,
    ayanamsha: float,
    anchor_lookback_interval: str,
    current_atr: float | None = None,
) -> FrozenSwingAnchor:
    swing_price, pivot_dt, pivot_type, lookback_high, lookback_low = identify_last_swing_pivot(
        df,
        interval_label=anchor_lookback_interval,
    )
    last_close = float(df["close"].iloc[-1])

    moon_deg = sidereal_longitude(ephem.Moon(), pivot_dt, ayanamsha)
    sun_deg = sidereal_longitude(ephem.Sun(), pivot_dt, ayanamsha)
    mars_deg = sidereal_longitude(ephem.Mars(), pivot_dt, ayanamsha)

    sun_anchor_price = swing_price
    anchor_price = swing_price

    static_anchor = anchor_price - (moon_deg * ppd)
    primary = static_anchor + (moon_deg * ppd)
    extremes = lattice_extremes_from_primary(primary, ppd, current_atr)
    upper = extremes["upper_lattice_node"]
    lower = extremes["lower_lattice_node"]
    exit_upper = extremes["exit_upper_node"]

    logger.info(
        "Sun anchor from %s %s: price=%.2f @ %s | CMP=%.2f (not used) | ppd=%.2f",
        anchor_lookback_interval,
        pivot_type,
        sun_anchor_price,
        pivot_dt.isoformat(),
        last_close,
        ppd,
    )

    return FrozenSwingAnchor(
        anchor_price=anchor_price,
        anchor_timestamp=pivot_dt,
        pivot_type=pivot_type,
        static_anchor=static_anchor,
        moon_degree_at_pivot=moon_deg,
        sun_degree_at_pivot=sun_deg,
        mars_degree_at_pivot=mars_deg,
        primary_vector_support=primary,
        upper_lattice_node=upper,
        lower_lattice_node=lower,
        exit_upper_node=exit_upper,
        sun_anchor_price=sun_anchor_price,
        lookback_high=lookback_high,
        lookback_low=lookback_low,
        anchor_lookback_interval=anchor_lookback_interval,
    )


def build_mw_vertices(
    frozen: FrozenSwingAnchor,
    ppd: float | None = None,
    current_atr: float | None = None,
) -> dict[str, Any]:
    """Build MW vertices; optional ppd/atr override frozen lattice prices for dynamic grid."""
    source = f"{frozen.anchor_lookback_interval}_last_swing"
    if ppd is not None and ppd != 0:
        moon = frozen.moon_degree_at_pivot
        static = frozen.anchor_price - (moon * ppd)
        primary = static + (moon * ppd)
        extremes = lattice_extremes_from_primary(primary, ppd, current_atr)
        exit_upper = extremes["exit_upper_node"]
        entry_upper = extremes["upper_lattice_node"]
        entry_lower = extremes["lower_lattice_node"]
        exit_lower = extremes["lower_lattice_node"]
    else:
        exit_upper = frozen.exit_upper_node
        entry_upper = frozen.upper_lattice_node
        entry_lower = frozen.lower_lattice_node
        exit_lower = frozen.lower_lattice_node

    return {
        "A": {
            "label": "A",
            "degree": frozen.moon_degree_at_pivot,
            "price": entry_upper,
            "role": "entry_ceiling",
        },
        "B": {
            "label": "B",
            "degree": frozen.moon_degree_at_pivot,
            "price": entry_lower,
            "role": "entry_floor",
        },
        "C": {
            "label": "C",
            "degree": frozen.sun_degree_at_pivot,
            "price": exit_upper,
            "role": "exit_peak",
        },
        "D": {
            "label": "D",
            "degree": frozen.sun_degree_at_pivot,
            "price": exit_lower,
            "role": "exit_floor",
        },
        "sun_crossing": {
            "label": "Sun",
            "degree": frozen.sun_degree_at_pivot,
            "price": frozen.sun_anchor_price,
            "anchor_price": frozen.sun_anchor_price,
            "role": "vector_cross",
            "source": source,
        },
    }


def validate_anchor_prices(
    frozen: FrozenSwingAnchor,
    live_price: float,
) -> list[str]:
    warnings: list[str] = []
    lo, hi = frozen.lookback_low, frozen.lookback_high
    margin = (hi - lo) * 0.15 if hi > lo else hi * 0.05
    interval = frozen.anchor_lookback_interval
    source_label = f"{interval}_last_swing"

    if abs(frozen.sun_anchor_price - live_price) < 0.01:
        warnings.append(
            f"Sun anchor price equals CMP ({live_price:.2f}) — anchor must be "
            f"{interval} swing, not live spot"
        )

    checks = [
        (f"Sun anchor ({interval} swing)", frozen.sun_anchor_price, source_label),
        ("Anchor pivot", frozen.anchor_price, source_label),
    ]
    for name, price, source in checks:
        if price < lo - margin or price > hi + margin:
            warnings.append(
                f"{name} price {price:.2f} (source={source}) outside lookback "
                f"range [{lo:.2f}, {hi:.2f}]"
            )

    if abs(frozen.anchor_price - live_price) > (hi - lo) * 2:
        logger.warning(
            "Grid divergence: sun_anchor=%.2f vs live_price=%.2f (gap=%.2f)",
            frozen.sun_anchor_price,
            live_price,
            abs(frozen.anchor_price - live_price),
        )
    return warnings
