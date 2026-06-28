"""Background matrix scanner and real-time signal broadcasting."""

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

SCAN_INTERVAL_SECONDS = 1


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
        message = json.dumps(payload)
        for connection in list(self.active_connections):
            try:
                await connection.send_text(message)
            except Exception:
                self.disconnect(connection)


matrix_manager = MatrixConnectionManager()


@dataclass(frozen=True)
class MatrixStreamConfig:
    symbol: str
    price_per_degree: float
    leverage: int


@dataclass
class MatrixStreamContext:
    scanner_task: asyncio.Task | None = None
    config: MatrixStreamConfig | None = None


async def _scan_once(
    symbol: str,
    price_per_degree: float,
    leverage: int,
    on_event: Callable[[dict[str, Any]], Awaitable[None]],
) -> None:
    try:
        engine = get_engine(
            symbol=symbol,
            price_per_degree=price_per_degree,
            leverage=leverage,
        )
        report = engine.run_matrix_scanner()
        marker_mgr = get_marker_manager(symbol)

        signal_status = report.get("signal", {}).get("status", "SCANNING")
        new_marker = marker_mgr.create_from_scan(report, signal_status)

        await on_event(
            {
                "event": "matrix_frame",
                "data": report,
            }
        )

        if new_marker:
            await on_event(
                {
                    "event": "matrix_signal",
                    "marker": new_marker.to_dict(),
                }
            )
    except Exception as exc:
        logger.error("Matrix scan failed for %s: %s", symbol, exc)
        await on_event(
            {
                "event": "matrix_error",
                "message": str(exc),
                "symbol": symbol,
            }
        )


async def _scanner_loop(
    symbol: str,
    price_per_degree: float,
    leverage: int,
) -> None:
    async def emit(payload: dict[str, Any]) -> None:
        await matrix_manager.broadcast(payload)

    while True:
        await _scan_once(symbol, price_per_degree, leverage, emit)
        await asyncio.sleep(SCAN_INTERVAL_SECONDS)


async def ensure_matrix_stream(
    ctx: MatrixStreamContext,
    symbol: str = "BTCUSDT",
    price_per_degree: float = 200.0,
    leverage: int = 50,
) -> None:
    """Keep a single background scanner aligned with the active symbol/settings."""
    sym = symbol.upper()
    desired = MatrixStreamConfig(sym, float(price_per_degree), int(leverage))
    if (
        ctx.config == desired
        and ctx.scanner_task is not None
        and not ctx.scanner_task.done()
    ):
        return

    await stop_matrix_stream(ctx)
    ctx.config = desired
    ctx.scanner_task = asyncio.create_task(
        _scanner_loop(sym, desired.price_per_degree, desired.leverage),
        name=f"matrix-scanner-{sym}",
    )
    logger.info(
        "Matrix scanner started for %s (ppd=%s, leverage=%s)",
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
    if ctx.scanner_task is not None:
        ctx.scanner_task.cancel()
        try:
            await ctx.scanner_task
        except asyncio.CancelledError:
            pass
        ctx.scanner_task = None
    ctx.config = None


async def websocket_matrix(
    websocket: WebSocket,
    symbol: str = "BTCUSDT",
    price_per_degree: float = 200.0,
    leverage: int = 50,
    stream_ctx: MatrixStreamContext | None = None,
) -> None:
    await matrix_manager.connect(websocket)
    sym = symbol.upper()

    marker_mgr = get_marker_manager(sym)
    await websocket.send_text(
        json.dumps(
            {
                "event": "matrix_history",
                "markers": marker_mgr.list_dicts(),
                "symbol": sym,
            }
        )
    )

    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        matrix_manager.disconnect(websocket)


async def trigger_manual_scan(
    symbol: str,
    price_per_degree: float,
    leverage: int,
) -> dict[str, Any]:
    """Run a single scan and broadcast results to connected clients."""

    events: list[dict[str, Any]] = []

    async def collect(payload: dict[str, Any]) -> None:
        events.append(payload)
        await matrix_manager.broadcast(payload)

    await _scan_once(symbol, price_per_degree, leverage, collect)
    frame = next((e for e in events if e.get("event") == "matrix_frame"), None)
    signal = next((e for e in events if e.get("event") == "matrix_signal"), None)
    return {
        "frame": frame,
        "signal": signal,
    }
