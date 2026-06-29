"""Volatility-responsive lattice band — no fixed macro price spacing."""

from __future__ import annotations

from typing import Any

import pandas as pd


def dynamic_lattice_half_band(ppd: float, current_atr: float | None) -> float:
    """
    Half-band between primary vector and upper/lower lattice nodes.

    Derived from dynamic PPD and live ATR:
      band_degrees = ATR / PPD
      half_band    = band_degrees × PPD = ATR

    When ATR is unavailable, fall back to a minimal PPD-scaled band.
    """
    if ppd <= 0:
        return 0.0
    if current_atr is None or pd.isna(current_atr) or float(current_atr) <= 0:
        return ppd * 6.665
    return float(current_atr)


def lattice_extremes_from_primary(
    primary: float,
    ppd: float,
    current_atr: float | None,
) -> dict[str, float]:
    """Compute upper, lower, and exit lattice nodes from primary + dynamic band."""
    half = dynamic_lattice_half_band(ppd, current_atr)
    upper = primary + half
    lower = primary - half
    return {
        "primary_vector_support": primary,
        "upper_lattice_node": upper,
        "lower_lattice_node": lower,
        "exit_upper_node": upper + half * 0.95,
        "lattice_half_band": half,
        "band_degrees": half / ppd if ppd > 0 else 0.0,
    }


HARMONIC_LEVELS = 5


def build_harmonic_nodes(
    primary: float,
    half_band: float,
    levels: int = HARMONIC_LEVELS,
) -> dict[str, list[dict[str, float | int | str]]]:
    """
    Split half_band into equal vertical steps (20% … 100%) above and below primary.

    H_up,n = P_primary + (n × half_band / 5)  for n ∈ {1..5}
    """
    if half_band <= 0 or levels <= 0:
        return {"upper": [], "lower": []}

    step = float(half_band) / float(levels)
    upper: list[dict[str, float | int | str]] = []
    lower: list[dict[str, float | int | str]] = []

    for n in range(1, levels + 1):
        pct = int((n / levels) * 100)
        upper.append({"n": n, "pct": pct, "price": round(primary + n * step, 2), "side": "upper"})
        lower.append({"n": n, "pct": pct, "price": round(primary - n * step, 2), "side": "lower"})

    return {"upper": upper, "lower": lower}


def lattice_extremes_meta(
    ppd: float,
    current_atr: float | None,
) -> dict[str, Any]:
    half = dynamic_lattice_half_band(ppd, current_atr)
    return {
        "lattice_half_band": round(half, 4),
        "band_degrees": round(half / ppd, 4) if ppd > 0 else 0.0,
        "band_source": "dynamic_ppd_atr" if current_atr and not pd.isna(current_atr) else "ppd_fallback",
    }
