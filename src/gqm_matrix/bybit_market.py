"""Shared Bybit v5 market data helpers (REST + order book state)."""

from __future__ import annotations

import json
import urllib.request
from typing import Any

import pandas as pd
import requests

BYBIT_REST = "https://api.bybit.com"
BYBIT_LINEAR_WS = "wss://stream.bybit.com/v5/public/linear"
BYBIT_SPOT_WS = "wss://stream.bybit.com/v5/public/spot"

INTERVAL_MAP = {
    "1m": "1",
    "3m": "3",
    "5m": "5",
    "15m": "15",
    "30m": "30",
    "1h": "60",
    "2h": "120",
    "4h": "240",
    "6h": "360",
    "12h": "720",
    "1d": "D",
    "1w": "W",
    "1M": "M",
}


class BybitOrderbook:
    """Maintain Bybit v5 order book from snapshot + delta messages."""

    def __init__(self) -> None:
        self.bids: dict[float, float] = {}
        self.asks: dict[float, float] = {}
        self.update_id: int | None = None
        self.timestamp_ms: int | None = None

    def apply_snapshot(self, data: dict[str, Any]) -> None:
        self.bids = {float(price): float(size) for price, size in data.get("b", []) if float(size) > 0}
        self.asks = {float(price): float(size) for price, size in data.get("a", []) if float(size) > 0}
        self.update_id = data.get("u")
        self.timestamp_ms = data.get("ts")

    def apply_delta(self, data: dict[str, Any]) -> None:
        for price_str, size_str in data.get("b", []):
            price = float(price_str)
            size = float(size_str)
            if size <= 0:
                self.bids.pop(price, None)
            else:
                self.bids[price] = size
        for price_str, size_str in data.get("a", []):
            price = float(price_str)
            size = float(size_str)
            if size <= 0:
                self.asks.pop(price, None)
            else:
                self.asks[price] = size
        self.update_id = data.get("u")
        self.timestamp_ms = data.get("ts")

    def levels(self, depth: int = 50) -> tuple[list[tuple[float, float]], list[tuple[float, float]]]:
        bids = sorted(self.bids.items(), key=lambda item: item[0], reverse=True)[:depth]
        asks = sorted(self.asks.items(), key=lambda item: item[0])[:depth]
        return bids, asks


def map_interval(interval: str) -> str:
    return INTERVAL_MAP.get(interval, interval)


def fetch_linear_klines_df(
    symbol: str,
    interval: str = "5m",
    limit: int = 20,
    atr_period: int = 14,
) -> pd.DataFrame | None:
    params = {
        "category": "linear",
        "symbol": symbol.upper(),
        "interval": map_interval(interval),
        "limit": limit,
    }
    try:
        response = requests.get(f"{BYBIT_REST}/v5/market/kline", params=params, timeout=10)
        response.raise_for_status()
        payload = response.json()
        rows = (payload.get("result") or {}).get("list") or []
        if not rows:
            return None

        rows.reverse()
        df = pd.DataFrame(
            rows,
            columns=[
                "open_time",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "turnover",
            ],
        )
        df["timestamp"] = pd.to_datetime(df["open_time"].astype(int), unit="ms", utc=True)
        df["close_time"] = df["open_time"].astype(int) + 1
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = df[col].astype(float)

        df["prev_close"] = df["close"].shift(1)
        df["tr1"] = df["high"] - df["low"]
        df["tr2"] = (df["high"] - df["prev_close"]).abs()
        df["tr3"] = (df["low"] - df["prev_close"]).abs()
        df["true_range"] = df[["tr1", "tr2", "tr3"]].max(axis=1)
        df["atr"] = df["true_range"].rolling(window=atr_period).mean()
        return df
    except Exception:
        return None


def fetch_linear_ticker(symbol: str = "BTCUSDT") -> tuple[float | None, str | None]:
    url = f"{BYBIT_REST}/v5/market/tickers?category=linear&symbol={symbol.upper()}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=3.0) as response:
            payload = json.loads(response.read().decode())
            rows = (payload.get("result") or {}).get("list") or []
            if not rows:
                return None, None
            last_price = rows[0].get("lastPrice")
            if last_price is None:
                return None, None
            return float(last_price), str(last_price)
    except Exception:
        return None, None


def fetch_linear_ohlcv_rows(
    symbol: str = "BTCUSDT",
    interval: str = "1h",
    limit: int = 4,
) -> list[list[object]]:
    params = {
        "category": "linear",
        "symbol": symbol.upper(),
        "interval": map_interval(interval),
        "limit": limit,
    }
    try:
        req = urllib.request.Request(
            f"{BYBIT_REST}/v5/market/kline?category=linear&symbol={params['symbol']}"
            f"&interval={params['interval']}&limit={limit}",
            headers={"User-Agent": "Mozilla/5.0"},
        )
        with urllib.request.urlopen(req, timeout=3.0) as response:
            payload = json.loads(response.read().decode())
            rows = (payload.get("result") or {}).get("list") or []
            if not rows:
                return []
            rows.reverse()
            # Binance-compatible shape: [open_time, open, high, low, close, volume, close_time, ...]
            converted: list[list[object]] = []
            for row in rows:
                converted.append(
                    [
                        int(row[0]),
                        row[1],
                        row[2],
                        row[3],
                        row[4],
                        row[5],
                        int(row[0]) + 1,
                    ]
                )
            return converted
    except Exception:
        return []
