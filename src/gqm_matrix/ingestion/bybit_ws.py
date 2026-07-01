from __future__ import annotations

import asyncio
import json

import websockets

from gqm_matrix.bybit_market import BYBIT_LINEAR_WS

LIQUIDATION_SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")


class BybitIngestionEngine:
    def __init__(self, redis_client) -> None:
        self.redis = redis_client
        self.ws_url = BYBIT_LINEAR_WS

    async def start_stream(self) -> None:
        topics = [f"allLiquidation.{symbol}" for symbol in LIQUIDATION_SYMBOLS]

        while True:
            try:
                print("[BYBIT] Connecting to live linear liquidation feed...")
                async with websockets.connect(self.ws_url, ping_interval=20, ping_timeout=20) as ws:
                    await ws.send(json.dumps({"op": "subscribe", "args": topics}))
                    print("[BYBIT] Stream connected successfully!")
                    while True:
                        message = await ws.recv()
                        envelope = json.loads(message)
                        if envelope.get("op") == "subscribe":
                            continue
                        if not str(envelope.get("topic", "")).startswith("allLiquidation."):
                            continue
                        for order in envelope.get("data") or []:
                            await self.process_liquidation(order)
            except websockets.exceptions.ConnectionClosed:
                print("[BYBIT] Connection lost. Reconnecting in 3 seconds...")
                await asyncio.sleep(3)
            except Exception as exc:
                print(f"[BYBIT] Stream error: {exc}")
                await asyncio.sleep(3)

    async def process_liquidation(self, order_data: dict) -> None:
        symbol = order_data.get("s")
        side_raw = str(order_data.get("S", ""))
        qty = float(order_data.get("v", 0))
        price = float(order_data.get("p", 0))
        usd_value = qty * price

        if usd_value <= 5000:
            return

        # Align with dashboard semantics: SELL = long wipe, BUY = short wipe.
        side = "SELL" if side_raw.lower() == "sell" else "BUY"
        payload = {
            "source": "bybit_linear",
            "type": "liquidation",
            "symbol": symbol,
            "side": side,
            "price": price,
            "usd_value": round(usd_value, 2),
        }
        print(f"[MARKET ALERT] {symbol} | {side} Liquidation: ${usd_value:,.2f}")
        await self.redis.publish("gqm_signals", json.dumps(payload))
