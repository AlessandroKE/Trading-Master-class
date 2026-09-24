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
class TimeframeView:
    timeframe: str
    last_close: float | None = None
    indicators: Indicators = field(default_factory=Indicators)


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
