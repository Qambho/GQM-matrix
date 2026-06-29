"""Order-book spoof detection — flags pulled walls with no matching aggTrade fill."""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SpoofAlert:
    price: float
    side: str
    pulled_size: float
    executed_size: float
    decay: float
    timestamp_ms: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "price": round(float(self.price), 2),
            "side": self.side,
            "pulled_size": round(float(self.pulled_size), 4),
            "executed_size": round(float(self.executed_size), 4),
            "decay": round(float(self.decay), 4),
            "timestamp_ms": int(self.timestamp_ms),
        }


@dataclass
class SpoofDetector:
    """Detect spoof zones by comparing depth removals to aggTrade fills."""

    atr_volume_baseline: float = 0.0
    spoof_multiplier: float = 3.0
    fill_ratio_threshold: float = 0.10
    decay_halflife_ms: float = 8000.0
    max_trade_history: int = 500

    _prev_bids: dict[float, float] = field(default_factory=dict)
    _prev_asks: dict[float, float] = field(default_factory=dict)
    _trades: deque = field(default_factory=lambda: deque(maxlen=500))
    _alerts: list[SpoofAlert] = field(default_factory=list)

    def record_trade(self, price: float, qty: float, timestamp_ms: int) -> None:
        self._trades.append(
            {
                "price": float(price),
                "qty": float(qty),
                "ts": int(timestamp_ms),
            }
        )

    def _executed_at_price(self, price: float, window_ms: int = 500) -> float:
        now = int(time.time() * 1000)
        total = 0.0
        for trade in self._trades:
            if abs(trade["price"] - price) < 0.01 and now - trade["ts"] <= window_ms:
                total += trade["qty"]
        return total

    def _check_removals(
        self,
        prev: dict[float, float],
        current: dict[float, float],
        side: str,
        timestamp_ms: int,
    ) -> None:
        baseline = max(self.atr_volume_baseline, 1e-9)
        threshold = baseline * self.spoof_multiplier

        for price, prev_qty in prev.items():
            curr_qty = current.get(price, 0.0)
            removed = prev_qty - curr_qty
            if removed < threshold:
                continue
            executed = self._executed_at_price(price)
            if executed >= removed * self.fill_ratio_threshold:
                continue
            self._alerts.append(
                SpoofAlert(
                    price=price,
                    side=side,
                    pulled_size=removed,
                    executed_size=executed,
                    decay=1.0,
                    timestamp_ms=timestamp_ms,
                )
            )

    def update_depth(
        self,
        bids: list[tuple[float, float]],
        asks: list[tuple[float, float]],
        timestamp_ms: int | None = None,
    ) -> None:
        ts = timestamp_ms or int(time.time() * 1000)
        bid_map = {round(float(p), 2): float(q) for p, q in bids[:10]}
        ask_map = {round(float(p), 2): float(q) for p, q in asks[:10]}

        if self._prev_bids:
            self._check_removals(self._prev_bids, bid_map, "bid", ts)
        if self._prev_asks:
            self._check_removals(self._prev_asks, ask_map, "ask", ts)

        self._prev_bids = bid_map
        self._prev_asks = ask_map

    def spoofed_volume_bid(self) -> float:
        now = int(time.time() * 1000)
        return sum(
            a.pulled_size
            for a in self._alerts
            if a.side == "bid" and now - a.timestamp_ms < self.decay_halflife_ms * 3
        )

    def spoofed_volume_ask(self) -> float:
        now = int(time.time() * 1000)
        return sum(
            a.pulled_size
            for a in self._alerts
            if a.side == "ask" and now - a.timestamp_ms < self.decay_halflife_ms * 3
        )

    def tick_decay(self) -> None:
        now = int(time.time() * 1000)
        alive: list[SpoofAlert] = []
        for alert in self._alerts:
            age_ms = now - alert.timestamp_ms
            alert.decay = max(0.0, 1.0 - age_ms / (self.decay_halflife_ms * 3))
            if alert.decay > 0.01:
                alive.append(alert)
        self._alerts = alive[-50:]

    def active_alerts(self) -> list[dict[str, Any]]:
        self.tick_decay()
        return [a.to_dict() for a in self._alerts if a.decay > 0.01]
