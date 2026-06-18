from __future__ import annotations

import asyncio
import json
import random


class ArkhamTelemetryEngine:
    def __init__(self, redis_client) -> None:
        self.redis = redis_client
        self.whales = [
            "0x71C...3a9 (Whale)",
            "Jump Trading",
            "Wintermute Dev",
            "0x3f5...b1a",
            "Vitalik VB",
        ]
        self.tokens = ["ETH", "WBTC", "LINK", "SOL", "USDC"]

    async def monitor_whale_flows(self) -> None:
        print("[ARKHAM] Free local telemetry simulator initialized active.")
        while True:
            try:
                await asyncio.sleep(random.randint(7, 12))
                await self.generate_mock_transfer()
            except Exception as exc:
                print(f"[ARKHAM] Simulation exception: {exc}")

    async def generate_mock_transfer(self) -> None:
        token = random.choice(self.tokens)
        usd_value = round(random.uniform(150000, 4500000), 2)

        payload = {
            "source": "arkham_chain_simulated",
            "type": "whale_flow",
            "from": random.choice(self.whales),
            "to": "Binance Deposit Hot Wallet",
            "token": token,
            "usd_value": usd_value,
        }

        print(
            f"[ON-CHAIN] Whale Alert: {payload['from']} sent "
            f"${usd_value:,.2f} worth of {token} to Binance."
        )
        await self.redis.publish("gqm_signals", json.dumps(payload))
