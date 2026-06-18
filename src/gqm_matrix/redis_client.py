from __future__ import annotations

import asyncio
import os

import redis.asyncio as aioredis

REDIS_HOST = os.getenv("REDIS_HOST", "127.0.0.1")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))


class MockPubSub:
    def __init__(self, queue: asyncio.Queue, subscribers: list[asyncio.Queue]) -> None:
        self.queue = queue
        self.subscribers = subscribers

    async def subscribe(self, channel: str) -> None:
        print(f"[SIMULATOR] Subscribed to in-memory channel: {channel}")

    async def listen(self):
        try:
            while True:
                msg = await self.queue.get()
                yield {"type": "message", "data": msg}
        finally:
            if self.queue in self.subscribers:
                self.subscribers.remove(self.queue)


class MockRedisClient:
    """Simulates a shared Redis hub in memory when no real server is running."""

    _listeners: list[asyncio.Queue] = []

    async def ping(self) -> bool:
        return True

    async def publish(self, channel: str, message: str) -> int:
        for queue in self._listeners:
            await queue.put(message)
        return 1

    def pubsub(self) -> MockPubSub:
        queue: asyncio.Queue = asyncio.Queue()
        self._listeners.append(queue)
        return MockPubSub(queue, self._listeners)

    async def close(self) -> None:
        pass


class RedisClientManager:
    def __init__(self) -> None:
        self.redis = None

    async def connect(self):
        try:
            print(f"[DATABASE] Attempting to find Redis at {REDIS_HOST}:{REDIS_PORT}...")
            self.redis = await aioredis.from_url(
                f"redis://{REDIS_HOST}:{REDIS_PORT}",
                decode_responses=True,
            )
            await self.redis.ping()
            print("[DATABASE] Real Redis database connected successfully!")
            return self.redis
        except Exception:
            print("[DATABASE] No local Redis server detected.")
            print("[SIMULATOR] Activating smart in-memory data routing layout...")
            self.redis = MockRedisClient()
            return self.redis

    async def close(self) -> None:
        if self.redis:
            await self.redis.close()
