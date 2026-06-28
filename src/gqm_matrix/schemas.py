from typing import Any

from pydantic import BaseModel, Field

class HealthResponse(BaseModel):
    status: str


class MatrixMarketSnapshot(BaseModel):
    live_price: float | None = None
    price: float
    high: float
    low: float
    atr: float | None
    atr_tolerance: float


class MatrixCelestialSnapshot(BaseModel):
    moon_degree: float
    mars_degree: float
    mercury_degree: float
    high_volume_aspect: bool
    moon_sign: str
    mars_sign: str
    mercury_sign: str
    confluence: dict[str, Any]


class MatrixGridSnapshot(BaseModel):
    nakshatra_active: str
    dasa_lord: str
    primary_vector_support: float
    upper_lattice_node: float
    lower_lattice_node: float
    static_anchor: float
    price_per_degree: float
    last_calibration: str | None


class MatrixDistances(BaseModel):
    to_primary: float
    to_upper: float


class MatrixSignal(BaseModel):
    status: str
    message: str


class MatrixTrade(BaseModel):
    entry_time: str
    bias: str
    entry: float
    leverage: int
    position_size: float
    sl: float
    liq_price: float
    effective_sl: float
    tp: float
    status: str
    exit_time: str | None = None
    exit_price: float | None = None
    pnl_amount: float | None = None
    pnl_pct_of_balance: float | None = None


class MatrixAccount(BaseModel):
    balance: float
    leverage: int
    risk_per_trade_pct: float


class MatrixScanResponse(BaseModel):
    symbol: str
    timestamp: str
    market: MatrixMarketSnapshot
    celestial: MatrixCelestialSnapshot
    grid: MatrixGridSnapshot
    distances: MatrixDistances
    signal: MatrixSignal
    anchor: dict[str, Any] | None = None
    mw_structure: dict[str, Any] | None = None
    anchor_validation: list[str] = Field(default_factory=list)
    active_trade: MatrixTrade | None = None
    account: MatrixAccount
    trade_history: list[MatrixTrade] = Field(default_factory=list)


class SignalMarkerResponse(BaseModel):
    id: str
    timestamp: str
    x_degree: float
    y_price: float
    signal_type: str
    color: str
    confidence: float
    metadata: dict[str, Any] = Field(default_factory=dict)


class MarkerListResponse(BaseModel):
    markers: list[SignalMarkerResponse]
    symbol: str
