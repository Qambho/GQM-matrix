"""Sidereal ephemeris via pyswisseph (Lahiri) with tiered caching."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any

import swisseph as swe

logger = logging.getLogger("CelestialEphemeris")

MOON_CACHE_SECONDS = 60
SUN_MARS_CACHE_SECONDS = 3600

swe.set_sid_mode(swe.SIDM_LAHIRI)

_PLANET_MAP = {
    "moon": swe.MOON,
    "sun": swe.SUN,
    "mars": swe.MARS,
    "mercury": swe.MERCURY,
}

_cache: dict[str, tuple[float, float]] = {}


def _to_jd(dt: datetime) -> float:
    utc_dt = dt.astimezone(timezone.utc) if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    return swe.julday(
        utc_dt.year,
        utc_dt.month,
        utc_dt.day,
        utc_dt.hour + utc_dt.minute / 60.0 + utc_dt.second / 3600.0,
    )


def _cache_ttl(body: str) -> float:
    if body == "moon":
        return MOON_CACHE_SECONDS
    return SUN_MARS_CACHE_SECONDS


def sidereal_longitude(body: str, dt: datetime) -> float:
    """Return sidereal ecliptic longitude (0–360°) for body at dt."""
    key = body.lower()
    if key not in _PLANET_MAP:
        raise ValueError(f"Unknown body: {body}")

    now = time.monotonic()
    cached = _cache.get(key)
    if cached is not None:
        value, ts = cached
        if now - ts < _cache_ttl(key):
            return value

    jd = _to_jd(dt)
    result, _ = swe.calc_ut(jd, _PLANET_MAP[key], swe.FLG_SIDEREAL)
    deg = float(result[0]) % 360.0
    _cache[key] = (deg, now)
    return deg


def celestial_snapshot(dt: datetime) -> dict[str, Any]:
    """Cached Moon / Sun / Mars / Mercury sidereal longitudes."""
    moon = sidereal_longitude("moon", dt)
    sun = sidereal_longitude("sun", dt)
    mars = sidereal_longitude("mars", dt)
    mercury = sidereal_longitude("mercury", dt)
    return {
        "moon_degree": moon,
        "sun_degree": sun,
        "mars_degree": mars,
        "mercury_degree": mercury,
    }


def invalidate_cache() -> None:
    _cache.clear()
