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
    volume: float | None = None
    spread: float | None = None
    best_bid: float | None = None
    best_ask: float | None = None
    obi_pct: float | None = None
    filtered_obi_pct: float | None = None
    bid_qty: float | None = None
    ask_qty: float | None = None
    normalized_x: float | None = None


class MatrixVortexSnapshot(BaseModel):
    price_root: int = 0
    time_root: int = 0
    volume_root: int = 0
    price_vortex: bool = False
    time_vortex: bool = False
    volume_vortex: bool = False
    any_vortex: bool = False


class SpoofAlert(BaseModel):
    price: float
    side: str
    pulled_size: float
    executed_size: float
    decay: float
    timestamp_ms: int


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
    static_anchor: float | None = None
    ppd_cal: float | None = None
    price_per_degree: float
    lattice_half_band: float | None = None
    band_degrees: float | None = None
    band_source: str | None = None
    last_calibration: str | None = None
    fallback_ppd: float | None = None
    dynamic_ppd: float | None = None
    ppd_source: str | None = None
    scaling_factor: float | None = None
    ppd_meta: dict[str, Any] | None = None
    atr_period: int | None = None
    anchor_interval: str | None = None
    swing_anchor_price: float | None = None
    moon_degree_at_pivot: float | None = None
    pivot_type: str | None = None
    last_anchor_candle_close: int | None = None
    near_harmonic: bool | None = None
    harmonics: dict[str, Any] | None = None


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
    timestamp_ms: int | None = None
    market: MatrixMarketSnapshot
    celestial: MatrixCelestialSnapshot
    grid: MatrixGridSnapshot
    distances: MatrixDistances
    signal: MatrixSignal
    anchor: dict[str, Any] | None = None
    mw_structure: dict[str, Any] | None = None
    anchor_validation: list[str] = Field(default_factory=list)
    vortex: MatrixVortexSnapshot | None = None
    spoof_alerts: list[SpoofAlert] = Field(default_factory=list)
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
