"""Dynamic Price-Per-Degree from micro-volatility and lunar velocity."""

from __future__ import annotations

from typing import Any

import pandas as pd

# Moon sidereal velocity scaled to a 5-minute bar (degrees per 5m).
MOON_VELOCITY_5M = 0.0458

DEFAULT_SCALING_FACTOR = 0.1
DEFAULT_MIN_PPD = 25.0
DEFAULT_MAX_PPD = 800.0
DEFAULT_ATR_PERIOD = 5


def calculate_dynamic_ppd(
    current_atr: float | None,
    *,
    moon_velocity_5m: float = MOON_VELOCITY_5M,
    scaling_factor: float = DEFAULT_SCALING_FACTOR,
    min_ppd: float = DEFAULT_MIN_PPD,
    max_ppd: float = DEFAULT_MAX_PPD,
    fallback_ppd: float = 200.0,
) -> tuple[float, dict[str, Any]]:
    """
    dynamic_ppd = (current_atr / moon_velocity_5m) * scaling_factor

    Result is clamped to [min_ppd, max_ppd]. Returns fallback when ATR is invalid.
    """
    meta: dict[str, Any] = {
        "moon_velocity_5m": moon_velocity_5m,
        "scaling_factor": scaling_factor,
        "min_ppd": min_ppd,
        "max_ppd": max_ppd,
        "fallback_ppd": fallback_ppd,
        "atr_period": DEFAULT_ATR_PERIOD,
    }

    if current_atr is None or pd.isna(current_atr) or float(current_atr) <= 0:
        meta.update({"source": "fallback", "reason": "invalid_atr"})
        return round(float(fallback_ppd), 4), meta

    if moon_velocity_5m <= 0:
        meta.update({"source": "fallback", "reason": "invalid_moon_velocity"})
        return round(float(fallback_ppd), 4), meta

    raw = (float(current_atr) / moon_velocity_5m) * scaling_factor
    clamped = max(min_ppd, min(max_ppd, raw))
    meta.update(
        {
            "source": "dynamic",
            "raw_ppd": round(raw, 4),
            "current_atr": round(float(current_atr), 4),
            "clamped": raw != clamped,
        }
    )
    return round(clamped, 4), meta
