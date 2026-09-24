"""Offline smoke tests — no network. Verify imports + indicator math."""
import pandas as pd

from src.indicators import ta


def _synthetic_df(n=250):
    # deterministic rising series with noise-free structure
    close = pd.Series([100 + i * 0.5 for i in range(n)], dtype=float)
    df = pd.DataFrame(
        {
            "ts": range(n),
            "open": close.shift(1).fillna(close),
            "high": close + 1,
            "low": close - 1,
            "close": close,
            "volume": pd.Series([1000 + i for i in range(n)], dtype=float),
        }
    )
    return df


def test_ema_tracks_rising_series():
    df = _synthetic_df()
    ind = ta.compute(df)
    assert ind.ema20 is not None and ind.ema50 is not None
    # in a steadily rising series, faster EMA sits above slower EMA
    assert ind.ema20 > ind.ema50 > ind.ema200


def test_rsi_bounds():
    df = _synthetic_df()
    ind = ta.compute(df)
    assert ind.rsi14 is not None
    assert 0.0 <= ind.rsi14 <= 100.0
    # a monotonically rising series should be strongly overbought
    assert ind.rsi14 > 70


def test_atr_positive():
    df = _synthetic_df()
    ind = ta.compute(df)
    assert ind.atr14 is not None and ind.atr14 > 0


def test_empty_df_safe():
    empty = pd.DataFrame(columns=["ts", "open", "high", "low", "close", "volume"])
    ind = ta.compute(empty)
    assert ind.ema20 is None
