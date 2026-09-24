"""Behavioral trade-journal analysis (§22), rule-based.

Pure function `analyze(trades)` over a list of trade dicts -> text report. Deterministic and
testable. This is the natural place to LATER add the Claude API (deferred) for narrative
coaching over the same computed signals — see build note at the bottom.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime

# Thresholds (align with system-prompt.md risk rules)
OVERTRADE_PER_DAY = 4          # more than this in a day = overtrading signal
REVENGE_WINDOW_H = 2.0         # a new trade within N hours of a loss = possible revenge
MAX_LEVERAGE = 10.0           # above this = excessive leverage
MAX_RISK_PCT = 1.5            # above this = over-risking (default is 0.5-1%)
MIN_TRADES = 3               # below this, not enough data to judge behavior


def _ts(row) -> datetime | None:
    try:
        return datetime.fromisoformat(row["ts"])
    except (TypeError, ValueError, KeyError):
        return None


def _num(x):
    return x if isinstance(x, (int, float)) else None


def analyze(trades: list[dict]) -> str:
    n = len(trades)
    if n < MIN_TRADES:
        return (f"JOURNAL ANALYSIS\n{'='*40}\n"
                f"Only {n} trade(s) logged - need at least {MIN_TRADES} to assess behavior. "
                f"Keep logging.")

    trades = sorted(trades, key=lambda r: r.get("ts") or "")
    results = [(r.get("result") or "").lower() for r in trades]
    wins = results.count("win")
    losses = results.count("loss")
    decided = wins + losses
    rs = [_num(r.get("r_multiple")) for r in trades if _num(r.get("r_multiple")) is not None]

    flags: list[str] = []      # (title, evidence)
    focus: list[str] = []

    # --- Overtrading ---
    by_day = Counter()
    for r in trades:
        t = _ts(r)
        if t:
            by_day[t.date()] += 1
    worst_day, worst_n = (by_day.most_common(1)[0] if by_day else (None, 0))
    if worst_n > OVERTRADE_PER_DAY:
        flags.append(("Overtrading",
                      f"{worst_n} trades on {worst_day} (> {OVERTRADE_PER_DAY}/day)."))
        focus.append("Cap trades per day; wait for A+ setups (capital preservation > frequency).")

    # --- Revenge trading (a trade soon after a loss) ---
    revenge = 0
    for prev, cur in zip(trades, trades[1:]):
        if (prev.get("result") or "").lower() == "loss":
            tp, tc = _ts(prev), _ts(cur)
            if tp and tc and 0 <= (tc - tp).total_seconds() / 3600 <= REVENGE_WINDOW_H:
                revenge += 1
    if revenge:
        flags.append(("Possible revenge trading",
                      f"{revenge} trade(s) opened within {REVENGE_WINDOW_H}h of a loss."))
        focus.append("Enforce a cooldown after a loss before the next entry.")

    # --- Excessive leverage ---
    over_lev = [r for r in trades if (_num(r.get("leverage")) or 0) > MAX_LEVERAGE]
    if over_lev:
        mx = max(_num(r.get("leverage")) or 0 for r in over_lev)
        flags.append(("Excessive leverage",
                      f"{len(over_lev)} trade(s) above {MAX_LEVERAGE}x (max {mx:g}x)."))
        focus.append("Lower leverage; use a wider logical stop + smaller size instead.")

    # --- Over-risking ---
    over_risk = [r for r in trades if (_num(r.get("risk_pct")) or 0) > MAX_RISK_PCT]
    if over_risk:
        flags.append(("Over-risking",
                      f"{len(over_risk)} trade(s) risked > {MAX_RISK_PCT}% of equity."))
        focus.append("Keep risk to 0.5-1% per trade.")

    # --- Win/loss R asymmetry (letting losers run / cutting winners early) ---
    paired = [(_num(r.get("r_multiple")), (r.get("result") or "").lower())
              for r in trades if _num(r.get("r_multiple")) is not None]
    win_rs = [rm for rm, res in paired if res == "win"]
    loss_rs = [rm for rm, res in paired if res == "loss"]
    avg_win = sum(win_rs) / len(win_rs) if win_rs else None
    avg_loss = sum(loss_rs) / len(loss_rs) if loss_rs else None
    if avg_win is not None and avg_loss is not None and abs(avg_loss) > avg_win:
        flags.append(("Unfavorable R asymmetry",
                      f"avg win +{avg_win:.2f}R vs avg loss {avg_loss:.2f}R - "
                      f"losers bigger than winners."))
        focus.append("Cut losers at the planned stop; let winners reach TP (don't cut early).")

    # --- Repeated mistake ---
    mistakes = Counter((r.get("mistake") or "").strip().lower()
                       for r in trades if (r.get("mistake") or "").strip())
    if mistakes:
        top_m, cnt = mistakes.most_common(1)[0]
        if cnt >= 2:
            flags.append(("Repeated mistake",
                          f'"{top_m}" logged {cnt} times.'))
            focus.append(f"Address the recurring mistake: {top_m}.")

    # --- Assemble report ---
    P = ["JOURNAL ANALYSIS", "=" * 40]
    win_rate = f"{wins/decided*100:.0f}%" if decided else "n/a"
    expectancy = f"{sum(rs)/len(rs):+.2f}R" if rs else "n/a"
    total_r = f"{sum(rs):+.2f}R" if rs else "n/a"
    P.append(f"Trades: {n} | Wins {wins} / Losses {losses} | Win rate {win_rate}")
    P.append(f"Expectancy: {expectancy}/trade | Total: {total_r}")
    if avg_win is not None:
        P.append(f"Avg win {avg_win:+.2f}R" +
                 (f" | Avg loss {avg_loss:.2f}R" if avg_loss is not None else ""))
    P.append("")

    P.append("BEHAVIORAL FLAGS")
    P.append("-" * 40)
    if flags:
        for title, ev in flags:
            P.append(f"- {title}: {ev}")
    else:
        P.append("None detected. Process looks disciplined over this sample.")
    P.append("")

    P.append("FOCUS (process improvement)")
    P.append("-" * 40)
    if focus:
        for i, f in enumerate(dict.fromkeys(focus), 1):   # de-dup, keep order
            P.append(f"{i}. {f}")
    else:
        P.append("Keep doing what you're doing; keep logging to build the sample.")
    P.append("")
    P.append("(Rule-based analysis. Decision-support, not financial advice.)")
    return "\n".join(P)


# --- FUTURE (deferred): add Claude here ---
# analyze() computes the signals; a claude_narrate(trades, signals) could turn them into
# personalized coaching prose. Kept rule-based for now per the P0 cost decision.
