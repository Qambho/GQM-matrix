from __future__ import annotations

from pydantic import BaseModel, Field


class MarketTickerResponse(BaseModel):
    symbol: str
    price: float
    price_change: float
    price_change_percent: float
    high_price: float
    low_price: float
    volume: float
    quote_volume: float


class AstroMatrixResponse(BaseModel):
    date_root: int
    bias: str
    base_band: float
    entry_zone: float
    standard_target: float
    network_node_target: float
    stop_loss: float


class BlueprintResponse(BaseModel):
    asset: str
    leverage: int
    market: MarketTickerResponse
    market_source: str
    current_price: float
    active_antardasa: str
    active_antardasa_abbrev: str | None = None
    signified_houses: list[int]
    kp_signifies_gain: bool
    upcoming_good_windows: list[str]
    matrix: AstroMatrixResponse
    notice: str
    generated_at: str


class HealthResponse(BaseModel):
    status: str
    market_api: str = Field(default="Binance USD-M Futures")


class SymbolListResponse(BaseModel):
    symbols: list[str]
    source: str = Field(default="Binance USD-M Futures")
