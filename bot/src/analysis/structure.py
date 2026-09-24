"""Market-structure detection (P2), price-action first (per system-prompt.md §5–6).

Deterministic swing detection -> trend classification (HH/HL vs LH/LL) -> BOS/CHoCH
-> support/resistance clustering. Pure pandas, no external TA lib.
"""
from __future__ import annotations

import pandas as pd

from src.models.types import StructureView


def find_swings(df: pd.DataFrame, window: int = 3) -> tuple[list[tuple[int, float]], list[tuple[int, float]]]:
    """Fractal swings: a swing high/low is a local extreme with `window` candles on each
    side strictly lower/higher. Returns (swing_highs, swing_lows) as (index, price)."""
    highs, lows = df["high"], df["low"]
    n = len(df)
    swing_highs: list[tuple[int, float]] = []
    swing_lows: list[tuple[int, float]] = []
    for i in range(window, n - window):
        hi = highs.iloc[i]
        lo = lows.iloc[i]
        left_h = highs.iloc[i - window:i]
        right_h = highs.iloc[i + 1:i + window + 1]
        left_l = lows.iloc[i - window:i]
        right_l = lows.iloc[i + 1:i + window + 1]
        if hi > left_h.max() and hi > right_h.max():
            swing_highs.append((i, float(hi)))
        if lo < left_l.min() and lo < right_l.min():
            swing_lows.append((i, float(lo)))
    return swing_highs, swing_lows


def classify_trend(swing_highs: list[tuple[int, float]],
                   swing_lows: list[tuple[int, float]]) -> str:
    """HH+HL -> uptrend, LH+LL -> downtrend, otherwise range."""
    if len(swing_highs) < 2 or len(swing_lows) < 2:
        return "range"
    hh = swing_highs[-1][1] > swing_highs[-2][1]
    lh = swing_highs[-1][1] < swing_highs[-2][1]
    hl = swing_lows[-1][1] > swing_lows[-2][1]
    ll = swing_lows[-1][1] < swing_lows[-2][1]
    if hh and hl:
        return "uptrend"
    if lh and ll:
        return "downtrend"
    return "range"


def detect_event(trend: str, last_close: float,
                 recent_sh: float | None, recent_sl: float | None) -> str | None:
    """Break of structure (continuation) vs change of character (against trend)."""
    if recent_sh is None or recent_sl is None:
        return None
    if trend == "uptrend" and last_close < recent_sl:
        return "CHoCH_down"
    if trend == "downtrend" and last_close > recent_sh:
        return "CHoCH_up"
    if last_close > recent_sh:
        return "BOS_up"
    if last_close < recent_sl:
        return "BOS_down"
    return None


def cluster_levels(prices: list[float], tol_pct: float = 0.7) -> list[float]:
    """Group nearby swing prices into S/R levels; return the cluster means, sorted."""
    if not prices:
        return []
    prices = sorted(prices)
    clusters: list[list[float]] = [[prices[0]]]
    for p in prices[1:]:
        if abs(p - clusters[-1][-1]) / clusters[-1][-1] <= tol_pct / 100.0:
            clusters[-1].append(p)
        else:
            clusters.append([p])
    return [sum(c) / len(c) for c in clusters]


def nearest_levels(levels: list[float], price: float) -> tuple[float | None, float | None]:
    """Return (nearest support below price, nearest resistance above price)."""
    below = [lv for lv in levels if lv < price]
    above = [lv for lv in levels if lv > price]
    support = max(below) if below else None
    resistance = min(above) if above else None
    return support, resistance


def analyze(df: pd.DataFrame, timeframe: str, window: int = 3,
            tol_pct: float = 0.7) -> StructureView:
    """Full structure read for one timeframe."""
    view = StructureView(timeframe=timeframe)
    if df is None or len(df) < window * 2 + 3:
        return view

    swing_highs, swing_lows = find_swings(df, window)
    view.trend = classify_trend(swing_highs, swing_lows)
    last_close = float(df["close"].iloc[-1])

    recent_sh = swing_highs[-1][1] if swing_highs else None
    recent_sl = swing_lows[-1][1] if swing_lows else None
    view.last_swing_high = recent_sh
    view.last_swing_low = recent_sl
    view.last_event = detect_event(view.trend, last_close, recent_sh, recent_sl)

    # S/R from recent swings (cap to the last ~10 of each to stay relevant)
    sh_prices = [p for _, p in swing_highs[-10:]]
    sl_prices = [p for _, p in swing_lows[-10:]]
    levels = cluster_levels(sh_prices + sl_prices, tol_pct)
    view.nearest_support, view.nearest_resistance = nearest_levels(levels, last_close)
    return view
