"""Typed data structures passed between layers."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Indicators:
    ema20: float | None = None
    ema50: float | None = None
    ema200: float | None = None
    rsi14: float | None = None
    atr14: float | None = None
    macd: float | None = None
    macd_signal: float | None = None
    vol_avg20: float | None = None


@dataclass
class Derivatives:
    funding_rate: float | None = None      # current perp funding (fraction, e.g. 0.0001)
    open_interest: float | None = None     # in base or contracts (exchange-dependent)
    oi_notional_usd: float | None = None
    source: str | None = None


@dataclass
class StructureView:
    """Market-structure read for one timeframe (P2)."""
    timeframe: str
    trend: str = "range"                   # uptrend / downtrend / range
    last_event: str | None = None          # BOS_up / BOS_down / CHoCH_up / CHoCH_down
    last_swing_high: float | None = None
    last_swing_low: float | None = None
    nearest_support: float | None = None
    nearest_resistance: float | None = None


@dataclass
class TimeframeView:
    timeframe: str
    last_close: float | None = None
    indicators: Indicators = field(default_factory=Indicators)
    structure: StructureView | None = None


@dataclass
class SetupIdea:
    """A concrete candidate trade (P2 → feeds P3 reporting)."""
    direction: str                         # LONG / SHORT
    setup_type: str                        # support bounce / resistance rejection / ...
    entry_low: float
    entry_high: float
    stop: float
    tp1: float
    tp2: float | None
    tp3: float | None
    rr: float                              # to TP1
    confidence: str                        # Very Strong ... No Setup
    reasons: list[str] = field(default_factory=list)
    main_risk: str | None = None
    status: str = "watch"                  # ready (price at/near entry) | watch (wait for level)
    distance_pct: float = 0.0              # signed % from current price to entry mid


@dataclass
class MarketSnapshot:
    """One coin's full picture at scan time."""
    symbol: str                 # exchange symbol, e.g. "BTC/USDT:USDT"
    base: str                   # "BTC"
    market_cap_rank: int | None = None
    price: float | None = None
    change_24h_pct: float | None = None
    timeframes: dict[str, TimeframeView] = field(default_factory=dict)
    derivatives: Derivatives = field(default_factory=Derivatives)
    exchange: str | None = None
    ts: str | None = None       # ISO timestamp of the scan
    errors: list[str] = field(default_factory=list)

    # --- P2 analysis outputs ---
    bias: str = "neutral"                  # bullish / bearish / neutral
    score: int = 0                         # 0..100 quality score (§15)
    classification: str = "No Setup"       # Very Strong ... No Setup
    setup: SetupIdea | None = None
