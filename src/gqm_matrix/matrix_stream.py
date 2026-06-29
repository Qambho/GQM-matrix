"""Background matrix live stream and real-time signal broadcasting."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from fastapi import WebSocket, WebSocketDisconnect

from gqm_matrix.godzilla_engine import get_engine
from gqm_matrix.markers import get_marker_manager

logger = logging.getLogger("MatrixStream")


class MatrixConnectionManager:
    def __init__(self) -> None:
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, payload: dict[str, Any]) -> None:
        if not self.active_connections:
            return
        message = json.dumps(payload)
        dead: list[WebSocket] = []
        for connection in list(self.active_connections):
            try:
                await connection.send_text(message)
            except Exception:
                dead.append(connection)
        for connection in dead:
            self.disconnect(connection)


matrix_manager = MatrixConnectionManager()


@dataclass(frozen=True)
class MatrixStreamConfig:
    symbol: str
    price_per_degree: float
    leverage: int


@dataclass
class MatrixStreamContext:
    stream_task: asyncio.Task | None = None
    config: MatrixStreamConfig | None = None


async def _live_stream_loop(
    symbol: str,
    price_per_degree: float,
    leverage: int,
) -> None:
    engine = get_engine(
        symbol=symbol,
        price_per_degree=price_per_degree,
        leverage=leverage,
    )
    marker_mgr = get_marker_manager(symbol)
    last_signal_status: str | None = None

    async def on_frame(payload: dict[str, Any]) -> None:
        nonlocal last_signal_status
        await matrix_manager.broadcast(payload)

        if payload.get("event") != "matrix_frame":
            return
        data = payload.get("data") or {}
        signal_status = data.get("signal", {}).get("status", "SCANNING")
        if signal_status == last_signal_status:
            return
        last_signal_status = signal_status
        new_marker = marker_mgr.create_from_scan(data, signal_status)
        if new_marker:
            await matrix_manager.broadcast(
                {
                    "event": "matrix_signal",
                    "marker": new_marker.to_dict(),
                }
            )

    await engine.run_live_stream(on_frame)


async def ensure_matrix_stream(
    ctx: MatrixStreamContext,
    symbol: str = "BTCUSDT",
    price_per_degree: float = 200.0,
    leverage: int = 50,
) -> None:
    sym = symbol.upper()
    desired = MatrixStreamConfig(sym, float(price_per_degree), int(leverage))
    if (
        ctx.config == desired
        and ctx.stream_task is not None
        and not ctx.stream_task.done()
    ):
        return

    await stop_matrix_stream(ctx)
    ctx.config = desired
    ctx.stream_task = asyncio.create_task(
        _live_stream_loop(sym, desired.price_per_degree, desired.leverage),
        name=f"matrix-live-{sym}",
    )
    logger.info(
        "Matrix live stream started for %s (ppd=%s, leverage=%s)",
        sym,
        desired.price_per_degree,
        desired.leverage,
    )


async def start_matrix_stream(
    ctx: MatrixStreamContext,
    symbol: str = "BTCUSDT",
    price_per_degree: float = 200.0,
    leverage: int = 50,
) -> None:
    await ensure_matrix_stream(ctx, symbol, price_per_degree, leverage)


async def stop_matrix_stream(ctx: MatrixStreamContext) -> None:
    if ctx.stream_task is not None:
        ctx.stream_task.cancel()
        try:
            await ctx.stream_task
        except asyncio.CancelledError:
            pass
        ctx.stream_task = None
    ctx.config = None


async def websocket_matrix(
    websocket: WebSocket,
    symbol: str = "BTCUSDT",
    price_per_degree: float = 200.0,
    leverage: int = 50,
    stream_ctx: MatrixStreamContext | None = None,
) -> None:
    sym = symbol.upper()
    ppd = float(price_per_degree)
    lev = int(leverage)

    if stream_ctx is not None:
        await ensure_matrix_stream(stream_ctx, sym, ppd, lev)

    try:
        await matrix_manager.connect(websocket)
    except Exception:
        logger.exception("Failed to accept matrix WebSocket for %s", sym)
        return

    marker_mgr = get_marker_manager(sym)
    try:
        await websocket.send_text(
            json.dumps(
                {
                    "event": "matrix_history",
                    "markers": marker_mgr.list_dicts(),
                    "symbol": sym,
                }
            )
        )
    except Exception:
        matrix_manager.disconnect(websocket)
        return

    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        logger.debug("Matrix WebSocket disconnected: %s", sym)
    except Exception as exc:
        logger.warning("Matrix WebSocket error (%s): %s", sym, exc)
    finally:
        matrix_manager.disconnect(websocket)


async def trigger_manual_scan(
    symbol: str,
    price_per_degree: float,
    leverage: int,
) -> dict[str, Any]:
    """Legacy one-shot scan — prefer /ws/matrix live stream."""
    engine = get_engine(
        symbol=symbol,
        price_per_degree=price_per_degree,
        leverage=leverage,
    )
    report = engine.run_matrix_scanner()
    marker_mgr = get_marker_manager(symbol)
    signal_status = report.get("signal", {}).get("status", "SCANNING")
    new_marker = marker_mgr.create_from_scan(report, signal_status)

    frame_event = {"event": "matrix_frame", "data": report}
    await matrix_manager.broadcast(frame_event)

    signal_event = None
    if new_marker:
        signal_event = {"event": "matrix_signal", "marker": new_marker.to_dict()}
        await matrix_manager.broadcast(signal_event)

    return {"frame": frame_event, "signal": signal_event}
