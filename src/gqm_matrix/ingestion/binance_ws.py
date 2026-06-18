from __future__ import annotations

import asyncio
import json

import websockets

BINANCE_WSS_URL = "wss://fstream.binance.com/ws"


class BinanceIngestionEngine:
    def __init__(self, redis_client) -> None:
        self.redis = redis_client
        self.stream_url = f"{BINANCE_WSS_URL}/!forceOrder@arr"

    async def start_stream(self) -> None:
        while True:
            try:
                print("[BINANCE] Connecting to live futures liquidation feed...")
                async with websockets.connect(self.stream_url) as ws:
                    print("[BINANCE] Stream connected successfully!")
                    while True:
                        message = await ws.recv()
                        data = json.loads(message)
                        await self.process_liquidation(data["o"])
            except websockets.exceptions.ConnectionClosed:
                print("[BINANCE] Connection lost. Reconnecting in 3 seconds...")
                await asyncio.sleep(3)
            except Exception as exc:
                print(f"[BINANCE] Stream error: {exc}")
                await asyncio.sleep(3)

    async def process_liquidation(self, order_data: dict) -> None:
        symbol = order_data.get("s")
        side = order_data.get("S")
        qty = float(order_data.get("q", 0))
        price = float(order_data.get("p", 0))
        usd_value = qty * price

        if usd_value > 5000:
            payload = {
                "source": "binance_futures",
                "type": "liquidation",
                "symbol": symbol,
                "side": side,
                "price": price,
                "usd_value": round(usd_value, 2),
            }
            print(f"[MARKET ALERT] {symbol} | {side} Liquidation: ${usd_value:,.2f}")
            await self.redis.publish("gqm_signals", json.dumps(payload))
