"""Rule-based report synthesis (P3) — assembles the system-prompt.md daily-report format
from analyzed snapshots. No LLM (deferred). Plain text; the delivery layer handles Telegram.

Honest by construction: sections that need later phases (live news/macro, liquidation
clusters, BTC-correlation stress) are labelled as not-yet-integrated rather than faked (§24).
"""
from __future__ import annotations

from datetime import datetime, timezone

from tabulate import tabulate

from src.models.types import MarketSnapshot


def _fmt(x, spec="4g"):
    return format(x, spec) if isinstance(x, (int, float)) else "-"


def _bias_of(snap: MarketSnapshot) -> str:
    return snap.bias


def _trend_str(snap: MarketSnapshot, tf: str) -> str:
    v = snap.timeframes.get(tf)
    if not v:
        return "n/a"
    struct = v.structure.trend if v.structure else "?"
    if v.last_close is not None and v.indicators.ema50 is not None:
        ema = "above EMA50" if v.last_close >= v.indicators.ema50 else "below EMA50"
    else:
        ema = "?"
    return f"{struct}, {ema}"


def _find(snaps, base):
    return next((s for s in snaps if s.base == base), None)


def _regime(snaps: list[MarketSnapshot], btc: MarketSnapshot | None) -> tuple[str, str, str]:
    """Return (regime, risk_env, breadth_note)."""
    n = len(snaps) or 1
    bullish = sum(1 for s in snaps if s.bias == "bullish")
    bearish = sum(1 for s in snaps if s.bias == "bearish")
    reds = sum(1 for s in snaps if (s.change_24h_pct or 0) < 0)
    breadth = f"{bullish}/{n} bullish bias, {bearish}/{n} bearish; {reds}/{n} red on 24h"

    btc_bull = btc is not None and btc.bias == "bullish"
    btc_bear = btc is not None and btc.bias == "bearish"

    if btc_bull and bullish > bearish and reds < n / 2:
        regime = "Bullish"
    elif btc_bull and reds >= n / 2:
        regime = "Bullish consolidation / pullback"
    elif btc_bear and bearish >= bullish:
        regime = "Bearish"
    elif bearish > bullish:
        regime = "Bearish consolidation"
    else:
        regime = "Neutral / range"

    # Risk: broad red + BTC not clearly trending => elevated
    if reds >= n * 0.6:
        risk = "Elevated (broad-based selling)"
    elif btc is not None and (btc.timeframes.get("1d") and
                              btc.timeframes["1d"].structure and
                              btc.timeframes["1d"].structure.trend == "range"):
        risk = "Moderate (BTC ranging)"
    else:
        risk = "Normal"
    return regime, risk, breadth


def _scan_table(snaps: list[MarketSnapshot]) -> str:
    rows = []
    for s in snaps:
        d1 = s.timeframes.get("1d")
        struct = d1.structure.trend if (d1 and d1.structure) else "-"
        fr = s.derivatives.funding_rate
        rows.append([
            s.market_cap_rank if s.market_cap_rank is not None else "?",
            s.base,
            _fmt(s.price),
            f"{s.change_24h_pct:+.1f}%" if s.change_24h_pct is not None else "-",
            struct,
            s.bias,
            f"{fr*100:.3f}%" if fr is not None else "-",
            f"{s.score} {s.classification}",
        ])
    headers = ["#", "Coin", "Price", "24h", "1D", "Bias", "Fund", "Score"]
    return tabulate(rows, headers=headers, tablefmt="presto")


def _setup_block(s: MarketSnapshot) -> str:
    u = s.setup
    dist = "AT ENTRY" if u.status == "ready" else f"{u.distance_pct:+.1f}% to entry"
    lines = [
        f"{s.base}/USDT  {u.direction}  [{u.confidence}]  ({u.setup_type})  | {dist}",
        f"  Entry {_fmt(u.entry_low)}-{_fmt(u.entry_high)} | Stop {_fmt(u.stop)} | "
        f"TP1 {_fmt(u.tp1)} / TP2 {_fmt(u.tp2)} / TP3 {_fmt(u.tp3)} | R:R {u.rr}",
        f"  Why: {'; '.join(u.reasons)}",
        f"  Main risk: {u.main_risk}",
    ]
    return "\n".join(lines)


def _execution_plan(btc: MarketSnapshot | None) -> str:
    if not btc or "1d" not in btc.timeframes or not btc.timeframes["1d"].structure:
        return "BTC structure unavailable — no execution levels."
    st = btc.timeframes["1d"].structure
    sup = _fmt(st.nearest_support)
    res = _fmt(st.nearest_resistance)
    return (
        f"BTC price {_fmt(btc.price)} | 1D structure: {st.trend}\n"
        f"  > BTC reclaims/holds above {res}  -> bullish continuation\n"
        f"  > BTC rejects {res}                -> favor shorts / risk-off\n"
        f"  > BTC loses {sup}                  -> bearish; stand aside on alt longs\n"
        f"  > BTC between {sup}-{res}          -> WAIT (range)"
    )


def build_report(snaps: list[MarketSnapshot], session: str = "") -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    btc = _find(snaps, "BTC")
    eth = _find(snaps, "ETH")
    regime, risk, breadth = _regime(snaps, btc)

    ready = [s for s in snaps if s.setup and s.setup.status == "ready"]
    watch = [s for s in snaps if s.setup and s.setup.status == "watch"]
    long_ready = [s for s in ready if s.setup.direction == "LONG"]
    short_ready = [s for s in ready if s.setup.direction == "SHORT"]

    # Verdict (§19.10)
    if ready:
        verdict = "TRADEABLE - actionable setup(s) at entry (confirm before executing)."
    elif watch:
        verdict = "WAIT FOR CONFIRMATION - aligned setups exist but price is not at entry."
    else:
        verdict = "NO TRADE - nothing cleared the quality filter. Preserve capital."

    P = []
    title = f"CRYPTO MARKET REPORT{(' - ' + session) if session else ''}"
    P.append(title)
    P.append("=" * len(title))
    P.append(f"Time:        {now}")
    P.append(f"Regime:      {regime}")
    P.append(f"BTC:         {_trend_str(btc, '1d') if btc else 'n/a'}"
             + (f"  ({_fmt(btc.price)})" if btc and btc.price else ""))
    P.append(f"ETH:         {_trend_str(eth, '1d') if eth else 'n/a'}")
    P.append(f"Risk env:    {risk}")
    P.append(f"Breadth:     {breadth}")
    P.append("")

    P.append("1. MARKET SUMMARY")
    P.append("-" * 40)
    summary = (
        f"Top-{len(snaps)} scan complete. Market breadth: {breadth}. "
        f"Overall regime read as '{regime}'. "
    )
    if ready:
        summary += f"{len(ready)} setup(s) at a tradeable entry, {len(watch)} on watch. "
    else:
        summary += f"No setup at entry; {len(watch)} on watch. "
    summary += ("NOTE: live news/macro (CPI/PCE/FOMC), liquidation clusters and "
                "BTC-correlation stress are NOT yet integrated (later phases) - factor "
                "event risk manually.")
    P.append(summary)
    P.append("")

    P.append("2. TOP MARKET SCAN")
    P.append("-" * 40)
    P.append(_scan_table(snaps))
    P.append("")

    P.append("3. BEST LONG SETUPS (at entry)")
    P.append("-" * 40)
    P.append("\n\n".join(_setup_block(s) for s in long_ready)
             if long_ready else "None at entry.")
    P.append("")

    P.append("4. BEST SHORT SETUPS (at entry)")
    P.append("-" * 40)
    P.append("\n\n".join(_setup_block(s) for s in short_ready)
             if short_ready else "None at entry.")
    P.append("")

    P.append("5. WATCHLIST (aligned, waiting for price to reach entry)")
    P.append("-" * 40)
    if watch:
        watch_sorted = sorted(watch, key=lambda s: abs(s.setup.distance_pct))[:5]
        P.append("\n\n".join(_setup_block(s) for s in watch_sorted))
    else:
        P.append("Empty.")
    P.append("")

    P.append("6. EXECUTION PLAN")
    P.append("-" * 40)
    P.append(_execution_plan(btc))
    P.append("")

    P.append("7. FINAL VERDICT")
    P.append("-" * 40)
    P.append(verdict)
    P.append("")
    P.append("(Rule-based synthesis, no LLM. Decision-support only, not financial advice.)")
    return "\n".join(P)
