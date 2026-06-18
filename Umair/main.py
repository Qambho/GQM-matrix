import asyncio
import uvicorn
from database.redis_client import RedisClientManager
from ingestion.binance_ws import BinanceIngestionEngine
from ingestion.arkham_client import ArkhamTelemetryEngine
from config import API_PORT

async def start_services():
    print("[CORE] Activating asynchronous trading core...")

    # 1. Create a dedicated Redis data connection for the ingestion tasks
    redis_manager = RedisClientManager()
    redis_client = await redis_manager.connect()

    # 2. Instantiate our high-frequency ingestion engines
    binance_engine = BinanceIngestionEngine(redis_client)
    arkham_engine = ArkhamTelemetryEngine(redis_client)

    # 3. Spin up the ingestion workers concurrently as non-blocking background tasks
    asyncio.create_task(binance_engine.start_stream())
    asyncio.create_task(arkham_engine.monitor_whale_flows())

    # 4. Configure and run the Uvicorn web gateway server
    config = uvicorn.Config(
        "api.server:app", 
        host="127.0.0.1", 
        port=API_PORT, 
        log_level="info"
    )
    server = uvicorn.Server(config)
    
    # Keeping this awaited prevents the main application loop from terminating
    await server.serve()

if __name__ == "__main__":
    try:
        asyncio.run(start_services())
    except KeyboardInterrupt:
        print("\n[CORE] Shutdown command received. Terminating all streams cleanly.")