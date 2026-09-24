"""Indicators in pure pandas (no pandas-ta, to avoid the numpy>=2 breakage).

Each function takes a pandas DataFrame with columns: ts, open, high, low, close, volume.
"""
from __future__ import annotations

import pandas as pd

from src.models.types import Indicators


def to_dataframe(ohlcv: list[list[float]]) -> pd.DataFrame:
    df = pd.DataFrame(ohlcv, columns=["ts", "open", "high", "low", "close", "volume"])
    df["ts"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    return df


def ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    # Wilder's smoothing
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss
    out = 100 - (100 / (1 + rs))
    # Edge cases where avg_loss == 0 (no downside): pure uptrend -> 100, flat -> 50.
    out = out.mask((avg_loss == 0) & (avg_gain > 0), 100.0)
    out = out.mask((avg_loss == 0) & (avg_gain == 0), 50.0)
    return out


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    tr = pd.concat(
        [(high - low), (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False).mean()


def macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    macd_line = ema(series, fast) - ema(series, slow)
    signal_line = ema(macd_line, signal)
    return macd_line, signal_line


def _last(series: pd.Series) -> float | None:
    if series is None or series.empty:
        return None
    val = series.iloc[-1]
    return None if pd.isna(val) else float(val)


def compute(df: pd.DataFrame) -> Indicators:
    """Compute the indicator bundle for the latest candle."""
    if df.empty:
        return Indicators()
    close = df["close"]
    macd_line, signal_line = macd(close)
    return Indicators(
        ema20=_last(ema(close, 20)),
        ema50=_last(ema(close, 50)),
        ema200=_last(ema(close, 200)),
        rsi14=_last(rsi(close, 14)),
        atr14=_last(atr(df, 14)),
        macd=_last(macd_line),
        macd_signal=_last(signal_line),
        vol_avg20=_last(df["volume"].rolling(20).mean()),
    )
