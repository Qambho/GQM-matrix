from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field

from fastapi import WebSocket, WebSocketDisconnect

from gqm_matrix.calcs_matrix import evaluate_matrix_pivot
from gqm_matrix.ingestion.arkham_client import ArkhamTelemetryEngine
from gqm_matrix.ingestion.binance_ws import BinanceIngestionEngine
from gqm_matrix.redis_client import RedisClientManager


class ConnectionManager:
    def __init__(self) -> None:
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections.append(websocket)
        print(f"[SERVER] New client connected. Active pipelines: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket) -> None:
        self.active_connections.remove(websocket)
        print(f"[SERVER] Client disconnected. Active pipelines: {len(self.active_connections)}")

    async def broadcast(self, message: str) -> None:
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception:
                pass


manager = ConnectionManager()


async def redis_pubsub_listener(redis) -> None:
    pubsub = redis.pubsub()
    await pubsub.subscribe("gqm_signals")
    print("[SERVER] Core PubSub matrix listening for live ingestion feeds...")

    try:
        async for message in pubsub.listen():
            if message["type"] != "message":
                continue

            raw_data = message["data"]
            if isinstance(raw_data, bytes):
                raw_data = raw_data.decode("utf-8")

            broadcast_payload = raw_data

            try:
                data_dict = json.loads(raw_data)
                price = (
                    data_dict.get("price")
                    or data_dict.get("live_price")
                    or data_dict.get("current_price")
                )

                if price is not None:
                    matrix_metrics = evaluate_matrix_pivot(float(price))
                    data_dict.update(matrix_metrics)
                    broadcast_payload = json.dumps(data_dict)
            except json.JSONDecodeError:
                try:
                    price = float(raw_data)
                    matrix_metrics = evaluate_matrix_pivot(price)
                    matrix_metrics["live_price"] = price
                    broadcast_payload = json.dumps(matrix_metrics)
                except ValueError:
                    pass

            await manager.broadcast(broadcast_payload)
    except asyncio.CancelledError:
        print("[SERVER] PubSub channel listener shut down cleanly.")


@dataclass
class LiveStreamContext:
    redis_manager: RedisClientManager = field(default_factory=RedisClientManager)
    listener_task: asyncio.Task | None = None
    ingestion_tasks: list[asyncio.Task] = field(default_factory=list)


async def start_live_stream() -> LiveStreamContext:
    ctx = LiveStreamContext()
    redis = await ctx.redis_manager.connect()

    binance_engine = BinanceIngestionEngine(redis)
    arkham_engine = ArkhamTelemetryEngine(redis)

    ctx.ingestion_tasks = [
        asyncio.create_task(binance_engine.start_stream()),
        asyncio.create_task(arkham_engine.monitor_whale_flows()),
    ]
    ctx.listener_task = asyncio.create_task(redis_pubsub_listener(redis))
    return ctx


async def stop_live_stream(ctx: LiveStreamContext) -> None:
    if ctx.listener_task:
        ctx.listener_task.cancel()
        try:
            await ctx.listener_task
        except asyncio.CancelledError:
            pass

    for task in ctx.ingestion_tasks:
        task.cancel()

    if ctx.ingestion_tasks:
        await asyncio.gather(*ctx.ingestion_tasks, return_exceptions=True)

    await ctx.redis_manager.close()


async def websocket_signals(websocket: WebSocket) -> None:
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
