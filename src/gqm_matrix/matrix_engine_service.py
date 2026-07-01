"""Background service wrapper for ``src/matrix_engine.py`` (logic unchanged)."""
from __future__ import annotations

import json
import sys
import threading
import time
import urllib.request
from pathlib import Path
from typing import Any

_SRC_DIR = Path(__file__).resolve().parents[1]
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

import matrix_engine  # noqa: E402
from gqm_matrix.bybit_market import fetch_linear_ohlcv_rows, fetch_linear_ticker

PROJECT_ROOT = Path(__file__).resolve().parents[2]
_ENGINE_THREAD_NAME = "geo-matrix-engine"
_DEPTH_THREAD_NAME = "geo-bybit-depth"
_engine_thread: threading.Thread | None = None
_depth_thread: threading.Thread | None = None
_start_lock = threading.Lock()
_original_print = None
BYBIT_DEPTH_SYMBOL = "BTCUSDT"
BYBIT_DEPTH_POLL_SECONDS = 0.5


def push_bybit_depth(bids: list[tuple[float, float]], asks: list[tuple[float, float]]) -> None:
    """Share live Bybit book depth with matrix_engine liquidity analysis."""
    matrix_engine.update_bybit_orderbook(bids, asks)


def _poll_bybit_depth_loop() -> None:
    while True:
        try:
            url = (
                "https://api.bybit.com/v5/market/orderbook"
                f"?category=spot&symbol={BYBIT_DEPTH_SYMBOL}&limit=50"
            )
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=3.0) as response:
                payload = json.loads(response.read().decode())
            result = (payload.get("result") or {})
            bids = [(float(p), float(q)) for p, q in result.get("b", [])[:50]]
            asks = [(float(p), float(q)) for p, q in result.get("a", [])[:50]]
            if bids or asks:
                push_bybit_depth(bids, asks)
        except Exception:
            pass
        time.sleep(BYBIT_DEPTH_POLL_SECONDS)


def _run_engine_headless() -> None:
    """Run the engine loop without flooding the server console."""
    import builtins

    global _original_print
    _original_print = builtins.print

    def _quiet_print(*args, **kwargs):
        if threading.current_thread().name == _ENGINE_THREAD_NAME:
            return
        _original_print(*args, **kwargs)

    matrix_engine.clear_screen = lambda: None  # type: ignore[misc, assignment]
    builtins.print = _quiet_print
    try:
        matrix_engine.main()
    finally:
        builtins.print = _original_print


def start_matrix_engine_service() -> None:
    """Run the matrix engine main loop in a background thread."""
    global _engine_thread, _depth_thread
    with _start_lock:
        if _depth_thread is None or not _depth_thread.is_alive():
            _depth_thread = threading.Thread(
                target=_poll_bybit_depth_loop,
                name=_DEPTH_THREAD_NAME,
                daemon=True,
            )
            _depth_thread.start()
        if _engine_thread is not None and _engine_thread.is_alive():
            return
        if hasattr(sys.stdout, "reconfigure"):
            try:
                sys.stdout.reconfigure(encoding="utf-8", errors="replace")
                sys.stderr.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass
        matrix_engine.ENGINE_CONFIG = matrix_engine.load_config()
        matrix_engine.parse_jagannatha_hora_block()
        matrix_engine.get_binance_price = fetch_linear_ticker  # type: ignore[attr-defined]
        matrix_engine.fetch_binance_ohlcv = fetch_linear_ohlcv_rows  # type: ignore[attr-defined]
        _engine_thread = threading.Thread(
            target=_run_engine_headless,
            name=_ENGINE_THREAD_NAME,
            daemon=True,
        )
        _engine_thread.start()


def is_running() -> bool:
    return _engine_thread is not None and _engine_thread.is_alive()


def get_metrics() -> dict[str, Any]:
    stream = matrix_engine.ENGINE_DATA_STREAM
    if not stream:
        return {"status": "initializing", "engine_running": is_running()}
    payload = dict(stream)
    payload["engine_running"] = is_running()
    return payload


def get_config() -> dict[str, Any]:
    config = matrix_engine.ENGINE_CONFIG or matrix_engine.load_config()
    return config.to_dict()


def update_dasa(raw_dasa: str) -> None:
    matrix_engine.parse_jagannatha_hora_block(raw_dasa)


def update_config(payload: dict[str, Any]) -> dict[str, Any]:
    updated = matrix_engine.EngineConfig.from_dict(payload)
    matrix_engine.ENGINE_CONFIG = updated
    config_path = PROJECT_ROOT / matrix_engine.CONFIG_FILE
    with open(config_path, "w", encoding="utf-8") as handle:
        json.dump(updated.to_dict(), handle, indent=2)
    return updated.to_dict()
