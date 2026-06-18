import asyncio
import json
import websockets
from config import BINANCE_WSS_URL

class BinanceIngestionEngine:
    def __init__(self, redis_client):
        self.redis = redis_client
        # Hook into the global futures liquidation stream array
        self.stream_url = f"{BINANCE_WSS_URL}/!forceOrder@arr"

    async def start_stream(self):
        while True:
            try:
                print("[BINANCE] Connecting to live futures liquidation feed...")
                async with websockets.connect(self.stream_url) as ws:
                    print("[BINANCE] Stream connected successfully!")
                    while True:
                        message = await ws.recv()
                        data = json.loads(message)
                        # Extract the inner order data frame ('o')
                        await self.process_liquidation(data['o'])
            except websockets.exceptions.ConnectionClosed:
                print("[BINANCE] Connection lost. Reconnecting in 3 seconds...")
                await asyncio.sleep(3)
            except Exception as e:
                print(f"[BINANCE] Stream error: {e}")
                await asyncio.sleep(3)

    async def process_liquidation(self, order_data):
        symbol = order_data.get('s')
        side = order_data.get('S')
        qty = float(order_data.get('q', 0))
        price = float(order_data.get('p', 0))
        usd_value = qty * price

        # Focus purely on substantial market liquidations (> $5,000 USD)
        if usd_value > 5000:
            payload = {
                "source": "binance_futures",
                "type": "liquidation",
                "symbol": symbol,
                "side": side,
                "price": price,
                "usd_value": round(usd_value, 2)
            }
            print(f"[MARKET ALERT] {symbol} | {side} Liquidation: ${usd_value:,.2f}")
            
            # Broadcast the signal instantly into the shared Redis network hub
            await self.redis.publish("gqm_signals", json.dumps(payload))