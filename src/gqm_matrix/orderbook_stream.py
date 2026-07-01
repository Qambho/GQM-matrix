"""Live dual-exchange order book stream (Binance Spot + Bybit Spot)."""

from __future__ import annotations

import asyncio
import json
import logging
import urllib.request
from dataclasses import dataclass, field
from typing import Any

import websockets
from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger("OrderbookStream")

BINANCE_SPOT_REST = "https://api.binance.com/api/v3/depth"
BYBIT_SPOT_WS = "wss://stream.bybit.com/v5/public/spot"
BOOK_DEPTH = 50
BINANCE_POLL_SECONDS = 0.5


class OrderbookConnectionManager:
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


orderbook_manager = OrderbookConnectionManager()


def _compute_obi(bid_vol: float, ask_vol: float) -> float:
    total = bid_vol + ask_vol
    if total <= 0:
        return 0.0
    return ((bid_vol - ask_vol) / total) * 100.0


def _levels_with_cumulative(levels: list[tuple[float, float]]) -> list[dict[str, float]]:
    rows: list[dict[str, float]] = []
    cum_qty = 0.0
    cum_notional = 0.0
    for price, qty in levels:
        notional = price * qty
        cum_qty += qty
        cum_notional += notional
        rows.append(
            {
                "price": round(price, 8),
                "qty": round(qty, 8),
                "notional": round(notional, 2),
                "cum_qty": round(cum_qty, 8),
                "cum_notional": round(cum_notional, 2),
            }
        )
    return rows


def build_book_snapshot(
    exchange: str,
    market: str,
    symbol: str,
    bids: list[tuple[float, float]],
    asks: list[tuple[float, float]],
    *,
    update_id: int | str | None = None,
    timestamp_ms: int | None = None,
    status: str = "live",
) -> dict[str, Any]:
    if not bids or not asks:
        return {
            "exchange": exchange,
            "market": market,
            "symbol": symbol,
            "status": "waiting",
            "levels": BOOK_DEPTH,
        }

    best_bid = bids[0][0]
    best_ask = asks[0][0]
    mid = (best_bid + best_ask) / 2.0
    spread = best_ask - best_bid
    spread_bps = (spread / mid * 10000.0) if mid > 0 else 0.0

    bid_vol = sum(qty for _, qty in bids)
    ask_vol = sum(qty for _, qty in asks)
    bid_notional = sum(price * qty for price, qty in bids)
    ask_notional = sum(price * qty for price, qty in asks)

    return {
        "exchange": exchange,
        "market": market,
        "symbol": symbol,
        "status": status,
        "levels": len(bids),
        "update_id": update_id,
        "timestamp_ms": timestamp_ms,
        "best_bid": round(best_bid, 8),
        "best_ask": round(best_ask, 8),
        "mid": round(mid, 8),
        "spread": round(spread, 8),
        "spread_bps": round(spread_bps, 4),
        "bid_volume": round(bid_vol, 8),
        "ask_volume": round(ask_vol, 8),
        "bid_notional": round(bid_notional, 2),
        "ask_notional": round(ask_notional, 2),
        "obi_pct": round(_compute_obi(bid_vol, ask_vol), 4),
        "bids": _levels_with_cumulative(bids),
        "asks": _levels_with_cumulative(asks),
    }


class BybitOrderbook:
    """Maintain Bybit v5 order book from snapshot + delta messages."""

    def __init__(self) -> None:
        self.bids: dict[float, float] = {}
        self.asks: dict[float, float] = {}
        self.update_id: int | None = None
        self.timestamp_ms: int | None = None

    def apply_snapshot(self, data: dict[str, Any]) -> None:
        self.bids = {float(price): float(size) for price, size in data.get("b", []) if float(size) > 0}
        self.asks = {float(price): float(size) for price, size in data.get("a", []) if float(size) > 0}
        self.update_id = data.get("u")
        self.timestamp_ms = data.get("ts")

    def apply_delta(self, data: dict[str, Any]) -> None:
        for price_str, size_str in data.get("b", []):
            price = float(price_str)
            size = float(size_str)
            if size <= 0:
                self.bids.pop(price, None)
            else:
                self.bids[price] = size
        for price_str, size_str in data.get("a", []):
            price = float(price_str)
            size = float(size_str)
            if size <= 0:
                self.asks.pop(price, None)
            else:
                self.asks[price] = size
        self.update_id = data.get("u")
        self.timestamp_ms = data.get("ts")

    def levels(self, depth: int = BOOK_DEPTH) -> tuple[list[tuple[float, float]], list[tuple[float, float]]]:
        bids = sorted(self.bids.items(), key=lambda item: item[0], reverse=True)[:depth]
        asks = sorted(self.asks.items(), key=lambda item: item[0])[:depth]
        return bids, asks


@dataclass(frozen=True)
class OrderbookStreamConfig:
    symbol: str


@dataclass
class OrderbookStreamContext:
    stream_task: asyncio.Task | None = None
    config: OrderbookStreamConfig | None = None
    binance_book: dict[str, Any] = field(default_factory=dict)
    bybit_book: dict[str, Any] = field(default_factory=dict)


async def _broadcast_combined(ctx: OrderbookStreamContext) -> None:
    await orderbook_manager.broadcast(
        {
            "event": "orderbook_frame",
            "symbol": ctx.config.symbol if ctx.config else "BTCUSDT",
            "binance": ctx.binance_book,
            "bybit": ctx.bybit_book,
        }
    )


async def _fetch_binance_depth(symbol: str) -> dict[str, Any]:
    url = f"{BINANCE_SPOT_REST}?symbol={symbol}&limit={BOOK_DEPTH}"

    def _request() -> dict[str, Any]:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=3.0) as response:
            payload = json.loads(response.read().decode())
            if isinstance(payload, dict):
                return payload
            return {}

    return await asyncio.to_thread(_request)


async def _binance_loop(symbol: str, ctx: OrderbookStreamContext) -> None:
    """Poll Binance Spot REST depth — reliable when public WS is blocked."""
    while True:
        try:
            payload = await _fetch_binance_depth(symbol)
            bids = [(float(price), float(qty)) for price, qty in payload.get("bids", [])[:BOOK_DEPTH]]
            asks = [(float(price), float(qty)) for price, qty in payload.get("asks", [])[:BOOK_DEPTH]]
            ctx.binance_book = build_book_snapshot(
                "Binance",
                "Spot",
                symbol,
                bids,
                asks,
                update_id=payload.get("lastUpdateId"),
            )
            await _broadcast_combined(ctx)
            await asyncio.sleep(BINANCE_POLL_SECONDS)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("Binance order book stream error (%s): %s", symbol, exc)
            ctx.binance_book = {
                "exchange": "Binance",
                "market": "Spot",
                "symbol": symbol,
                "status": "reconnecting",
                "levels": BOOK_DEPTH,
            }
            await _broadcast_combined(ctx)
            await asyncio.sleep(3)


async def _bybit_loop(symbol: str, ctx: OrderbookStreamContext) -> None:
    topic = f"orderbook.{BOOK_DEPTH}.{symbol}"
    book = BybitOrderbook()

    while True:
        try:
            async with websockets.connect(BYBIT_SPOT_WS, ping_interval=20, ping_timeout=20) as ws:
                await ws.send(json.dumps({"op": "subscribe", "args": [topic]}))
                logger.info("Bybit order book connected: %s", symbol)
                while True:
                    raw = await ws.recv()
                    envelope = json.loads(raw)
                    if envelope.get("op") == "subscribe":
                        continue
                    if envelope.get("topic") != topic:
                        continue

                    msg_type = envelope.get("type")
                    data = envelope.get("data") or {}
                    if msg_type == "snapshot":
                        book.apply_snapshot(data)
                    elif msg_type == "delta":
                        book.apply_delta(data)
                    else:
                        continue

                    bids, asks = book.levels(BOOK_DEPTH)
                    try:
                        from gqm_matrix.matrix_engine_service import push_bybit_depth

                        push_bybit_depth(bids, asks)
                    except Exception:
                        pass
                    ctx.bybit_book = build_book_snapshot(
                        "Bybit",
                        "Spot",
                        symbol,
                        bids,
                        asks,
                        update_id=book.update_id,
                        timestamp_ms=int(book.timestamp_ms or envelope.get("ts") or 0) or None,
                    )
                    await _broadcast_combined(ctx)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("Bybit order book stream error (%s): %s", symbol, exc)
            ctx.bybit_book = {
                "exchange": "Bybit",
                "market": "Spot",
                "symbol": symbol,
                "status": "reconnecting",
                "levels": BOOK_DEPTH,
            }
            await _broadcast_combined(ctx)
            await asyncio.sleep(3)


async def _orderbook_stream_loop(symbol: str, ctx: OrderbookStreamContext) -> None:
    ctx.binance_book = {
        "exchange": "Binance",
        "market": "Spot",
        "symbol": symbol,
        "status": "connecting",
        "levels": BOOK_DEPTH,
    }
    ctx.bybit_book = {
        "exchange": "Bybit",
        "market": "Spot",
        "symbol": symbol,
        "status": "connecting",
        "levels": BOOK_DEPTH,
    }
    await _broadcast_combined(ctx)
    await asyncio.gather(_binance_loop(symbol, ctx), _bybit_loop(symbol, ctx))


async def ensure_orderbook_stream(ctx: OrderbookStreamContext, symbol: str) -> None:
    sym = symbol.upper()
    desired = OrderbookStreamConfig(sym)
    if ctx.config == desired and ctx.stream_task is not None and not ctx.stream_task.done():
        return

    await stop_orderbook_stream(ctx)
    ctx.config = desired
    ctx.stream_task = asyncio.create_task(
        _orderbook_stream_loop(sym, ctx),
        name=f"orderbook-live-{sym}",
    )
    logger.info("Order book stream started for %s", sym)


async def stop_orderbook_stream(ctx: OrderbookStreamContext) -> None:
    if ctx.stream_task is not None:
        ctx.stream_task.cancel()
        try:
            await ctx.stream_task
        except asyncio.CancelledError:
            pass
        ctx.stream_task = None
    ctx.config = None
    ctx.binance_book = {}
    ctx.bybit_book = {}


async def websocket_orderbook(
    websocket: WebSocket,
    symbol: str = "BTCUSDT",
    stream_ctx: OrderbookStreamContext | None = None,
) -> None:
    sym = symbol.upper()
    ctx = stream_ctx or OrderbookStreamContext()
    await ensure_orderbook_stream(ctx, sym)

    try:
        await orderbook_manager.connect(websocket)
    except Exception:
        logger.exception("Failed to accept order book WebSocket for %s", sym)
        return

    try:
        await websocket.send_text(
            json.dumps(
                {
                    "event": "orderbook_history",
                    "symbol": sym,
                    "binance": ctx.binance_book,
                    "bybit": ctx.bybit_book,
                }
            )
        )
    except Exception:
        orderbook_manager.disconnect(websocket)
        return

    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        logger.debug("Order book WebSocket disconnected: %s", sym)
    except Exception as exc:
        logger.warning("Order book WebSocket error (%s): %s", sym, exc)
    finally:
        orderbook_manager.disconnect(websocket)
