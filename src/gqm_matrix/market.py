from __future__ import annotations

from typing import Any

import requests

BINANCE_FUTURES_BASE = "https://fapi.binance.com"


class BinanceMarketClient:
    """Public Binance USD-M Futures market data client (no API key required)."""

    def __init__(self, base_url: str = BINANCE_FUTURES_BASE, timeout: int = 10) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        response = requests.get(
            f"{self.base_url}{path}",
            params=params,
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()

    def get_price(self, symbol: str) -> float:
        payload = self._get("/fapi/v1/ticker/price", {"symbol": symbol.upper()})
        return float(payload["price"])

    def get_24h_ticker(self, symbol: str) -> dict[str, Any]:
        payload = self._get("/fapi/v1/ticker/24hr", {"symbol": symbol.upper()})
        return {
            "symbol": payload["symbol"],
            "price": float(payload["lastPrice"]),
            "price_change": float(payload["priceChange"]),
            "price_change_percent": float(payload["priceChangePercent"]),
            "high_price": float(payload["highPrice"]),
            "low_price": float(payload["lowPrice"]),
            "volume": float(payload["volume"]),
            "quote_volume": float(payload["quoteVolume"]),
        }

    def list_symbols(self, quote_asset: str = "USDT") -> list[str]:
        payload = self._get("/fapi/v1/exchangeInfo")
        quote = quote_asset.upper()
        return sorted(
            symbol["symbol"]
            for symbol in payload["symbols"]
            if symbol.get("status") == "TRADING" and symbol["symbol"].endswith(quote)
        )
