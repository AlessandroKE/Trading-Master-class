"""Offline tests for structure detection and scoring — no network."""
import numpy as np
import pandas as pd

from src.analysis import scoring, structure
from src.indicators import ta
from src.models.types import Indicators, MarketSnapshot, TimeframeView


def _df(closes):
    close = pd.Series(closes, dtype=float)
    return pd.DataFrame(
        {
            "ts": range(len(closes)),
            "open": close.shift(1).fillna(close),
            "high": close + 0.5,
            "low": close - 0.5,
            "close": close,
            "volume": [1000.0] * len(closes),
        }
    )


def _from_pivots(pivots, step=6):
    """Interpolate linear ramps between pivots so each pivot is an isolated swing."""
    out: list[float] = []
    for a, b in zip(pivots, pivots[1:]):
        out.extend(np.linspace(a, b, step, endpoint=False).tolist())
    out.append(float(pivots[-1]))
    return out


def _zigzag_up(n=None):
    # HH + HL staircase: alternating higher highs and higher lows
    pivots = [100, 112, 106, 124, 118, 136, 130, 148, 142, 160]
    return _from_pivots(pivots)


def test_uptrend_detected():
    df = _df(_zigzag_up())
    view = structure.analyze(df, "1d")
    assert view.trend == "uptrend"
    assert view.last_swing_high is not None and view.last_swing_low is not None


def test_downtrend_detected():
    df = _df(list(reversed(_zigzag_up())))
    view = structure.analyze(df, "1d")
    assert view.trend == "downtrend"


def test_cluster_and_nearest_levels():
    levels = structure.cluster_levels([100, 100.3, 105, 110, 110.2], tol_pct=0.7)
    # 100/100.3 merge, 110/110.2 merge -> 3 levels
    assert len(levels) == 3
    sup, res = structure.nearest_levels(levels, 107.0)
    assert sup == 105 and round(res, 1) == 110.1


def test_no_trade_gate_on_conflict():
    # neutral bias must yield no setup
    snap = MarketSnapshot(symbol="X/USDT:USDT", base="X", price=100.0)
    snap.timeframes["1d"] = TimeframeView("1d", last_close=100.0,
                                          indicators=Indicators(ema50=100.0, ema200=100.0))
    snap.timeframes["4h"] = TimeframeView("4h", last_close=100.0,
                                          indicators=Indicators(ema50=100.0, ema200=100.0))
    scoring.evaluate(snap)
    assert snap.setup is None
    assert snap.classification in ("No Setup", "Weak")


def test_rr_respected_when_setup_built():
    # if a setup is produced, it must clear the min R:R
    df_up = _df(_zigzag_up(160))
    snap = MarketSnapshot(symbol="Y/USDT:USDT", base="Y")
    for tf in ("1d", "4h"):
        v = TimeframeView(tf, last_close=float(df_up["close"].iloc[-1]))
        v.indicators = ta.compute(df_up)
        v.structure = structure.analyze(df_up, tf)
        snap.timeframes[tf] = v
    snap.price = float(df_up["close"].iloc[-1])
    scoring.evaluate(snap)
    if snap.setup is not None:
        assert snap.setup.rr >= scoring.MIN_RR
