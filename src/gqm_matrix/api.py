from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from gqm_matrix.jh_engine import GqmMatrixJHEngineV72
from gqm_matrix.live_stream import start_live_stream, stop_live_stream, websocket_signals
from gqm_matrix.market import BinanceMarketClient
from gqm_matrix.schemas import BlueprintResponse, HealthResponse, MarketTickerResponse, SymbolListResponse

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIR = PROJECT_ROOT / "frontend"
DATA_DIR = PROJECT_ROOT / "data"


@asynccontextmanager
async def lifespan(app: FastAPI):
    live_ctx = await start_live_stream()
    app.state.live_ctx = live_ctx
    yield
    await stop_live_stream(live_ctx)


app = FastAPI(
    title="GQM Matrix Platform",
    description="Unified GQM platform: JH Engine blueprint + live data streamer.",
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

market_client = BinanceMarketClient()


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@app.get("/api/market/symbols", response_model=SymbolListResponse)
def list_symbols(quote: str = Query(default="USDT")) -> SymbolListResponse:
    try:
        symbols = market_client.list_symbols(quote_asset=quote)
        return SymbolListResponse(symbols=symbols[:50])
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Binance symbol list unavailable: {exc}") from exc


@app.get("/api/market/price")
def get_price(symbol: str = Query(default="BTCUSDT")) -> dict[str, float | str]:
    try:
        price = market_client.get_price(symbol)
        return {"symbol": symbol.upper(), "price": price, "source": "Binance USD-M Futures"}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Binance price unavailable: {exc}") from exc


@app.get("/api/market/ticker", response_model=MarketTickerResponse)
def get_ticker(symbol: str = Query(default="BTCUSDT")) -> MarketTickerResponse:
    try:
        return MarketTickerResponse(**market_client.get_24h_ticker(symbol))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Binance ticker unavailable: {exc}") from exc


@app.get("/api/blueprint", response_model=BlueprintResponse)
def get_blueprint(
    base_asset: str = Query(default="BTCUSDT"),
    leverage: int = Query(default=50, ge=1, le=125),
) -> BlueprintResponse:
    try:
        engine = GqmMatrixJHEngineV72(
            base_asset=base_asset,
            leverage=leverage,
            data_dir=DATA_DIR,
            market_client=market_client,
        )
        report = engine.generate_blueprint_report()
        return BlueprintResponse(**report)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail=f"Missing data file: {exc.filename}") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Blueprint generation failed: {exc}") from exc


@app.websocket("/ws/signals")
async def ws_signals(websocket: WebSocket) -> None:
    await websocket_signals(websocket)


@app.get("/")
def serve_frontend() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html")


if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")
