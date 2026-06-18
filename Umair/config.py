import os
from dotenv import load_dotenv

# Load environment variables from the .env file
load_dotenv()

# Network Settings
REDIS_HOST = os.getenv("REDIS_HOST", "127.0.0.1")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
API_PORT = int(os.getenv("API_PORT", 8000))

# API Streams
BINANCE_WSS_URL = "wss://fstream.binance.com/ws"