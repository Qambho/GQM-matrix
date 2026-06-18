import asyncio
import redis.asyncio as aioredis
from config import REDIS_HOST, REDIS_PORT

class MockPubSub:
    def __init__(self, queue, subscribers):
        self.queue = queue
        self.subscribers = subscribers

    async def subscribe(self, channel):
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
    """Simulates a shared Redis network hub in memory if no real server is running."""
    _listeners = []

    async def ping(self):
        return True

    async def publish(self, channel, message):
        for queue in self._listeners:
            await queue.put(message)
        return 1

    def pubsub(self):
        queue = asyncio.Queue()
        self._listeners.append(queue)
        return MockPubSub(queue, self._listeners)

    async def close(self):
        pass

class RedisClientManager:
    def __init__(self):
        self.redis = None

    async def connect(self):
        try:
            print(f"[DATABASE] Attempting to find Redis at {REDIS_HOST}:{REDIS_PORT}...")
            self.redis = await aioredis.from_url(
                f"redis://{REDIS_HOST}:{REDIS_PORT}", 
                decode_responses=True
            )
            # Try to ping the real server
            await self.redis.ping()
            print("[DATABASE] Real Redis database connected successfully!")
            return self.redis
        except Exception:
            print("[DATABASE] No local Redis server detected.")
            print("[SIMULATOR] Activating smart in-memory data routing layout...")
            self.redis = MockRedisClient()
            return self.redis

    async def close(self):
        if self.redis:
            await self.redis.close()