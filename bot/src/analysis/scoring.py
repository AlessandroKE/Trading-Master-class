"""Quality filter (§15) + candidate setup builder, with a hard NO-TRADE gate (§15/§25).

Deterministic scoring over the evidence we currently compute. Dimensions that need later
phases (news, macro, liquidations, BTC correlation) are STUBBED and noted — the score is
conservative without them, which is the correct bias (capital preservation first).

Scoring philosophy: reward *alignment* (HTF + intermediate structure + EMA + location agree)
and *good trade location* (price near a level, not mid-range). Punish conflict and extremes.
"""
from __future__ import annotations

from src.models.types import MarketSnapshot, SetupIdea, TimeframeView

# Confidence bands (per system-prompt.md §11 — buckets, never fake %)
BANDS = [
    (80, "Very Strong"),
    (65, "Strong"),
    (50, "Moderate"),
    (35, "Weak"),
    (0, "No Setup"),
]

MIN_RR = 1.5            # reject setups below this (prompt prefers ~1:2)
MIN_TRADEABLE = 50      # below "Moderate" => no setup surfaced
NEAR_LEVEL_PCT = 3.0    # price must be within this % of a level for good location
READY_BAND_PCT = 1.5    # within this % of the entry zone => "ready" (else "watch")
WATCH_MAX_DIST_PCT = 15.0  # beyond this, the level is too far to be a useful watch


def _band(score: int) -> str:
    for threshold, label in BANDS:
        if score >= threshold:
            return label
    return "No Setup"


def _ema_bias(tf: TimeframeView | None) -> str:
    if not tf or tf.last_close is None or tf.indicators.ema50 is None:
        return "neutral"
    ind = tf.indicators
    price = tf.last_close
    if ind.ema200 is not None:
        if price > ind.ema50 > ind.ema200:
            return "bullish"
        if price < ind.ema50 < ind.ema200:
            return "bearish"
    return "bullish" if price >= ind.ema50 else "bearish"


def _struct_bias(tf: TimeframeView | None) -> str:
    if not tf or tf.structure is None:
        return "neutral"
    return {"uptrend": "bullish", "downtrend": "bearish"}.get(tf.structure.trend, "neutral")


def evaluate(snap: MarketSnapshot) -> None:
    """Populate snap.bias, snap.score, snap.classification, snap.setup (in place)."""
    d1 = snap.timeframes.get("1d")
    h4 = snap.timeframes.get("4h")

    d1_ema, d1_struct = _ema_bias(d1), _struct_bias(d1)
    h4_ema = _ema_bias(h4)

    # --- Directional bias: HTF-led (1D structure + 1D EMA), confirmed by 4H EMA ---
    votes = [d1_struct, d1_ema, h4_ema]
    bull = votes.count("bullish")
    bear = votes.count("bearish")
    if bull >= 2 and bear == 0:
        snap.bias = "bullish"
    elif bear >= 2 and bull == 0:
        snap.bias = "bearish"
    else:
        snap.bias = "neutral"

    score, reasons = _score(snap, d1, h4, d1_struct, d1_ema, h4_ema)
    snap.score = score
    snap.classification = _band(score)

    # --- NO-TRADE gate ---
    if snap.bias == "neutral" or score < MIN_TRADEABLE:
        snap.setup = None
        snap.classification = _band(score) if score >= MIN_TRADEABLE else "No Setup"
        return

    setup = _build_setup(snap, d1, h4, reasons)
    if setup is None or setup.rr < MIN_RR:
        snap.setup = None
        snap.classification = "No Setup"
        return

    # --- Immediacy + staleness (per §5 WAIT zones / §12 entry strategy) ---
    price = snap.price
    # A setup whose invalidation is already breached is stale, not tradeable.
    if setup.direction == "LONG" and price <= setup.stop:
        snap.setup = None
        snap.classification = "No Setup"
        return
    if setup.direction == "SHORT" and price >= setup.stop:
        snap.setup = None
        snap.classification = "No Setup"
        return

    mid = (setup.entry_low + setup.entry_high) / 2
    setup.distance_pct = (price - mid) / mid * 100
    near = READY_BAND_PCT / 100.0
    in_zone = setup.entry_low * (1 - near) <= price <= setup.entry_high * (1 + near)
    setup.status = "ready" if in_zone else "watch"

    # Entry too far to be a useful watch => treat as no clean location (no setup).
    if setup.status == "watch" and abs(setup.distance_pct) > WATCH_MAX_DIST_PCT:
        snap.setup = None
        snap.classification = "No Setup"
        return

    setup.confidence = snap.classification
    snap.setup = setup


def _score(snap, d1, h4, d1_struct, d1_ema, h4_ema) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []

    # 1. HTF structure clear (not range)  [0-20]
    if d1_struct in ("bullish", "bearish"):
        score += 20
        reasons.append(f"1D structure {d1.structure.trend}")

    # 2. EMA alignment on 1D  [0-15]
    if d1_ema in ("bullish", "bearish") and d1_ema == d1_struct:
        score += 15
        reasons.append("1D EMA aligned with structure")
    elif d1_ema in ("bullish", "bearish"):
        score += 7

    # 3. 4H confirms 1D  [0-15]
    if h4_ema == d1_ema and h4_ema != "neutral":
        score += 15
        reasons.append("4H confirms 1D bias")

    # 4. Trade location: price near a relevant level  [0-25]  (the big one)
    loc = _location_score(snap, d1)
    score += loc[0]
    if loc[1]:
        reasons.append(loc[1])

    # 5. Momentum not exhausted against the trade (RSI)  [0-10]
    rsi = d1.indicators.rsi14 if d1 else None
    if rsi is not None:
        if d1_ema == "bullish" and rsi < 72:
            score += 10
        elif d1_ema == "bearish" and rsi > 28:
            score += 10
        else:
            reasons.append(f"RSI extreme ({rsi:.0f}) — momentum risk")

    # 6. Funding not crowded against the trade  [0-10]
    fr = snap.derivatives.funding_rate
    if fr is not None:
        # crowded longs (very +) hurt a long; crowded shorts (very -) hurt a short
        if d1_ema == "bullish" and fr < 0.0005:
            score += 10
        elif d1_ema == "bearish" and fr > -0.0005:
            score += 10
        else:
            reasons.append(f"funding crowded ({fr*100:.3f}%)")

    # 7. Derivatives data present (OI)  [0-5]
    if snap.derivatives.oi_notional_usd:
        score += 5

    # NOTE (stubbed, pending later phases): news/macro event risk, liquidation clusters,
    # BTC correlation. Their absence keeps the ceiling conservative — intentional.
    return min(score, 100), reasons


def _location_score(snap, d1) -> tuple[int, str | None]:
    """Reward price sitting near the level it would trade from; punish mid-range."""
    if not d1 or d1.structure is None or snap.price is None:
        return 0, None
    price = snap.price
    sup = d1.structure.nearest_support
    res = d1.structure.nearest_resistance

    def within(level):
        return level is not None and abs(price - level) / price * 100 <= NEAR_LEVEL_PCT

    if snap.bias == "bullish" and within(sup):
        return 25, f"price near 1D support {sup:,.4g}"
    if snap.bias == "bearish" and within(res):
        return 25, f"price near 1D resistance {res:,.4g}"
    # near the wrong side (e.g. bullish but pinned under resistance) = poor location
    if snap.bias == "bullish" and within(res):
        return 5, "bullish but pinned under resistance (poor location)"
    if snap.bias == "bearish" and within(sup):
        return 5, "bearish but sitting on support (poor location)"
    return 0, "mid-range (no clean location)"


def _build_setup(snap, d1, h4, reasons) -> SetupIdea | None:
    """Construct entry/stop/TPs from structure + ATR. Returns None if geometry is unusable."""
    if not d1 or d1.structure is None or snap.price is None:
        return None
    price = snap.price
    st = d1.structure
    atr = (h4.indicators.atr14 if h4 else None) or (d1.indicators.atr14 if d1 else None)
    if not atr:
        return None

    if snap.bias == "bullish":
        support = st.nearest_support
        if support is None:
            return None
        entry_low, entry_high = support, support + 0.5 * atr
        stop = (st.last_swing_low or support) - 0.5 * atr
        entry = (entry_low + entry_high) / 2
        if entry <= stop:
            return None
        tp1 = st.nearest_resistance or (entry + 2 * (entry - stop))
        tp2 = tp1 + 1.5 * (entry - stop)
        tp3 = tp1 + 3.0 * (entry - stop)
        rr = (tp1 - entry) / (entry - stop)
        return SetupIdea("LONG", "support bounce / structure continuation",
                         entry_low, entry_high, stop, tp1, tp2, tp3, round(rr, 2),
                         "", list(reasons),
                         "BTC rollover / support fails (confirm before entry)")

    # bearish
    resistance = st.nearest_resistance
    if resistance is None:
        return None
    entry_high, entry_low = resistance, resistance - 0.5 * atr
    stop = (st.last_swing_high or resistance) + 0.5 * atr
    entry = (entry_low + entry_high) / 2
    if stop <= entry:
        return None
    tp1 = st.nearest_support or (entry - 2 * (stop - entry))
    tp2 = tp1 - 1.5 * (stop - entry)
    tp3 = tp1 - 3.0 * (stop - entry)
    rr = (entry - tp1) / (stop - entry)
    return SetupIdea("SHORT", "resistance rejection",
                     entry_low, entry_high, stop, tp1, tp2, tp3, round(rr, 2),
                     "", list(reasons),
                     "short squeeze / BTC rips (confirm rejection before entry)")
