from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from gqm_matrix.godzilla_engine import get_engine
from gqm_matrix.live_stream import start_live_stream, stop_live_stream, websocket_signals
from gqm_matrix.markers import get_marker_manager
from gqm_matrix.matrix_stream import (
    MatrixStreamContext,
    matrix_manager,
    stop_matrix_stream,
    trigger_manual_scan,
    websocket_matrix,
)
from gqm_matrix.schemas import HealthResponse, MarkerListResponse, MatrixScanResponse, SignalMarkerResponse

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIR = PROJECT_ROOT / "frontend"
_matrix_stream_ctx = MatrixStreamContext()


@asynccontextmanager
async def lifespan(app: FastAPI):
    live_ctx = await start_live_stream()
    app.state.live_ctx = live_ctx
    app.state.matrix_stream_ctx = _matrix_stream_ctx
    yield
    await stop_matrix_stream(_matrix_stream_ctx)
    await stop_live_stream(live_ctx)


app = FastAPI(
    title="GQM Astro-Quant Platform",
    description="Live liquidation and whale-flow streamer with astro-quant confluence analysis.",
    version="1.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@app.get("/api/matrix/markers", response_model=MarkerListResponse)
def list_matrix_markers(symbol: str = Query(default="BTCUSDT")) -> MarkerListResponse:
    mgr = get_marker_manager(symbol)
    return MarkerListResponse(
        symbol=symbol.upper(),
        markers=[SignalMarkerResponse(**m) for m in mgr.list_dicts()],
    )


@app.get("/api/matrix/scan", response_model=MatrixScanResponse)
async def matrix_scan(
    symbol: str = Query(default="BTCUSDT"),
    price_per_degree: float = Query(default=200.0, ge=1.0),
    leverage: int = Query(default=50, ge=1, le=125),
) -> MatrixScanResponse:
    try:
        result = await trigger_manual_scan(
            symbol,
            price_per_degree,
            leverage,
        )
        frame_event = result.get("frame")
        if frame_event and frame_event.get("data"):
            return MatrixScanResponse(**frame_event["data"])
        engine = get_engine(symbol=symbol, price_per_degree=price_per_degree, leverage=leverage)
        report = engine.run_matrix_scanner()
        return MatrixScanResponse(**report)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Matrix scan failed: {exc}") from exc


@app.websocket("/ws/matrix")
async def ws_matrix(
    websocket: WebSocket,
    symbol: str = Query(default="BTCUSDT"),
    price_per_degree: float = Query(default=200.0),
    leverage: int = Query(default=50),
) -> None:
    sym = symbol.upper()
    await websocket_matrix(
        websocket,
        symbol=sym,
        price_per_degree=price_per_degree,
        leverage=leverage,
        stream_ctx=_matrix_stream_ctx,
    )


@app.websocket("/ws/signals")
async def ws_signals(websocket: WebSocket) -> None:
    await websocket_signals(websocket)


@app.get("/styles.css")
def serve_styles() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "styles.css", media_type="text/css")


@app.get("/app.js")
def serve_app_js() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "app.js", media_type="application/javascript")


@app.get("/")
def serve_frontend() -> FileResponse:
    return FileResponse(
        FRONTEND_DIR / "index.html",
        media_type="text/html",
        headers={"Cache-Control": "no-cache"},
    )


if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")
