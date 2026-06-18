from calcs_matrix import evaluate_matrix_pivot
import asyncio
import json
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from database.redis_client import RedisClientManager

# Manage the global state client instance cleanly
redis_manager = RedisClientManager()

class ConnectionManager:
    def __init__(self):
        # Keep track of all active browser/client WebSocket channels
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        print(f"[SERVER] New client connected. Active pipelines: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
        print(f"[SERVER] Client disconnected. Active pipelines: {len(self.active_connections)}")

    async def broadcast(self, message: str):
        # Ship data frames out to all connected terminals concurrently
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception:
                # Handle stale/dead browser connections gracefully
                pass

manager = ConnectionManager()

async def redis_pubsub_listener(redis):
    pubsub = redis.pubsub()
    await pubsub.subscribe("gqm_signals")
    print("[SERVER] Core PubSub matrix listening for live ingestion feeds...")
    
    try:
        async for message in pubsub.listen():
            if message["type"] == "message":
                # Extract the raw payload data from the Redis channel string
                raw_data = message["data"]
                if isinstance(raw_data, bytes):
                    raw_data = raw_data.decode("utf-8")
                
                broadcast_payload = raw_data
                
                try:
                    # Case A: If ingestion data arrives as an aggregated JSON string
                    data_dict = json.loads(raw_data)
                    
                    # Search for any valid structural price key in the payload object
                    price = data_dict.get("price") or data_dict.get("live_price") or data_dict.get("current_price")
                    
                    if price is not None:
                        # Compute your GQM paper indicators inline on the live feed tick
                        matrix_metrics = evaluate_matrix_pivot(float(price))
                        # Merge the pivot data parameters directly into the broadcast envelope
                        data_dict.update(matrix_metrics)
                        broadcast_payload = json.dumps(data_dict)
                        
                except json.JSONDecodeError:
                    # Case B: Fallback check if the incoming data is a standalone raw numeric tick
                    try:
                        price = float(raw_data)
                        matrix_metrics = evaluate_matrix_pivot(price)
                        matrix_metrics["live_price"] = price
                        broadcast_payload = json.dumps(matrix_metrics)
                    except ValueError:
                        # If it's a structural message without numeric values, pass it as-is
                        pass
                
                # Instantly catch incoming events and broadcast to all connected web clients
                await manager.broadcast(broadcast_payload)
                
    except asyncio.CancelledError:
        print("[SERVER] PubSub channel listener shut down cleanly.")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # This block executes when the server boots up
    redis = await redis_manager.connect()
    listener_task = asyncio.create_task(redis_pubsub_listener(redis))
    yield
    # This block executes when the server shuts down
    listener_task.cancel()
    await redis_manager.close()

# Initialize FastAPI with modern lifespan state tracking
app = FastAPI(title="GQM Live Data Streamer", lifespan=lifespan)

@app.websocket("/ws/signals")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # Keep client connection open and listen for basic keep-alive heartbeats
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)