"""Signal marker storage and lifecycle management."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

from gqm_matrix.coordinates import CoordinateGenerator, MatrixCoordinate
from gqm_matrix.utc_time import utc_provider

logger = logging.getLogger("MarkerManager")

SIGNAL_COLORS = {
    "BUY": "#34d399",
    "SELL": "#fb7185",
    "NEUTRAL": "#22d3ee",
}

STATUS_TO_SIGNAL = {
    "LONG_CONFLUENCE": "BUY",
    "SHORT_CONFLUENCE": "SELL",
    "IN_TRADE": None,
}


@dataclass
class SignalMarker:
    timestamp: str
    x_degree: float
    y_price: float
    signal_type: str
    color: str
    confidence: float
    metadata: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "x_degree": self.x_degree,
            "y_price": self.y_price,
            "signal_type": self.signal_type,
            "color": self.color,
            "confidence": self.confidence,
            "metadata": self.metadata,
        }


class MarkerManager:
    """Stores every signal marker; prevents duplicate emissions."""

    def __init__(self, max_markers: int = 2000) -> None:
        self._markers: list[SignalMarker] = []
        self._max_markers = max_markers
        self._last_signal_key: str | None = None
        self._last_signal_time: str | None = None
        self._last_signal_status: str | None = None

    @property
    def markers(self) -> list[SignalMarker]:
        return list(self._markers)

    def add(self, marker: SignalMarker) -> SignalMarker:
        if self._is_duplicate(marker):
            logger.debug("Duplicate signal suppressed: %s", marker.signal_type)
            return marker
        self._markers.append(marker)
        if len(self._markers) > self._max_markers:
            self._markers = self._markers[-self._max_markers:]
        self._last_signal_key = self._dedupe_key(marker)
        self._last_signal_time = marker.timestamp
        return marker

    def create_from_scan(
        self,
        report: dict[str, Any],
        signal_status: str,
    ) -> SignalMarker | None:
        prev_status = self._last_signal_status
        self._last_signal_status = signal_status

        if signal_status in ("LONG_CONFLUENCE", "SHORT_CONFLUENCE", "IN_TRADE"):
            if prev_status == signal_status:
                return None
        else:
            return None

        signal_type = STATUS_TO_SIGNAL.get(signal_status)
        if signal_type is None:
            if signal_status == "IN_TRADE" and report.get("active_trade"):
                bias = report["active_trade"].get("bias", "")
                signal_type = "BUY" if bias == "LONG" else "SELL" if bias == "SHORT" else "NEUTRAL"
            else:
                return None

        try:
            coord_gen = CoordinateGenerator.from_scan_report(report)
            coord = coord_gen.coordinate_from_scan(report)
        except (KeyError, ValueError, TypeError) as exc:
            logger.warning("Coordinate generation failed: %s", exc)
            return None

        confidence = self._estimate_confidence(report, signal_type)
        timestamp = report.get("timestamp") or utc_provider.iso_now()

        marker = SignalMarker(
            timestamp=timestamp,
            x_degree=coord.x_degree,
            y_price=coord.y_price,
            signal_type=signal_type,
            color=SIGNAL_COLORS.get(signal_type, SIGNAL_COLORS["NEUTRAL"]),
            confidence=confidence,
            metadata={
                "symbol": report.get("symbol"),
                "signal_status": signal_status,
                "moon_degree": report.get("celestial", {}).get("moon_degree"),
                "mars_degree": report.get("celestial", {}).get("mars_degree"),
                "spot_zodiac_degree": coord_gen.price_to_zodiac_degree(
                    report["market"]["price"]
                ),
                "nakshatra": report.get("grid", {}).get("nakshatra_active"),
                "message": report.get("signal", {}).get("message"),
            },
        )
        return self.add(marker)

    def _estimate_confidence(self, report: dict[str, Any], signal_type: str) -> float:
        tol = report.get("market", {}).get("atr_tolerance") or 1
        distances = report.get("distances", {})
        dist = distances.get("to_primary", tol) if signal_type == "BUY" else distances.get(
            "to_upper", tol
        )
        proximity = max(0.0, 1.0 - (dist / (tol * 2)))
        aspect_boost = 0.15 if report.get("celestial", {}).get("high_volume_aspect") else 0.0
        return round(min(0.99, 0.55 + proximity * 0.35 + aspect_boost), 2)

    def _dedupe_key(self, marker: SignalMarker) -> str:
        return f"{marker.signal_type}:{marker.x_degree:.2f}:{marker.y_price:.2f}"

    def _is_duplicate(self, marker: SignalMarker) -> bool:
        key = self._dedupe_key(marker)
        if self._last_signal_key == key and self._last_signal_time == marker.timestamp:
            return True
        if self._last_signal_key == key:
            return True
        return False

    def list_dicts(self) -> list[dict[str, Any]]:
        return [m.to_dict() for m in self._markers]

    def clear(self) -> None:
        self._markers.clear()
        self._last_signal_key = None
        self._last_signal_time = None


# Per-symbol marker stores
_marker_stores: dict[str, MarkerManager] = {}


def get_marker_manager(symbol: str = "BTCUSDT") -> MarkerManager:
    key = symbol.upper()
    if key not in _marker_stores:
        _marker_stores[key] = MarkerManager()
    return _marker_stores[key]
