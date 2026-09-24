"""Journal CLI (§22): log completed trades and run behavioral analysis.

Usage:
  python -m src.journal add --asset BTC --dir LONG --entry 83000 --stop 81000 \
      --exit 88000 --size 200 --lev 3 --risk 1 --result win --setup "support bounce" \
      --reason "1D uptrend pullback" --notes "clean"
  python -m src.journal list [--limit 20]
  python -m src.journal analyze [--limit 100] [--send]
"""
from __future__ import annotations

import argparse
import sys

from src.delivery import telegram
from src.journal import analyze as analyzer
from src.journal import store
from src.storage import db


def _safe_stdout() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass


def cmd_add(args) -> None:
    trade = {
        "asset": args.asset, "direction": args.dir, "entry": args.entry, "stop": args.stop,
        "tp": args.tp, "exit_price": args.exit, "size_usd": args.size, "leverage": args.lev,
        "risk_pct": args.risk, "result": args.result, "setup_type": args.setup,
        "reason": args.reason, "mistake": args.mistake, "notes": args.notes,
    }
    tid = store.add_trade(trade)
    row = store.recent(1)[-1]
    r = row.get("r_multiple")
    print(f"Logged trade #{tid}: {args.asset} {args.dir} result={args.result}"
          + (f" ({r:+.2f}R)" if isinstance(r, (int, float)) else ""))


def cmd_list(args) -> None:
    rows = store.recent(args.limit)
    if not rows:
        print("No trades logged yet.")
        return
    print(f"{'ts':20} {'asset':6} {'dir':5} {'result':6} {'R':>6}  setup")
    for r in rows:
        rm = r.get("r_multiple")
        rstr = f"{rm:+.2f}" if isinstance(rm, (int, float)) else "-"
        print(f"{(r.get('ts') or '')[:19]:20} {str(r.get('asset'))[:6]:6} "
              f"{str(r.get('direction'))[:5]:5} {str(r.get('result'))[:6]:6} "
              f"{rstr:>6}  {r.get('setup_type') or ''}")


def cmd_analyze(args) -> None:
    report = analyzer.analyze(store.recent(args.limit))
    print(report)
    if args.send and telegram.is_configured():
        telegram.send(report)
        print("\n(sent to Telegram)")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m src.journal", description="Trade journal (§22)")
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("add", help="log a completed trade")
    a.add_argument("--asset", required=True)
    a.add_argument("--dir", required=True, choices=["LONG", "SHORT"])
    a.add_argument("--entry", type=float)
    a.add_argument("--stop", type=float)
    a.add_argument("--tp", type=float)
    a.add_argument("--exit", type=float)
    a.add_argument("--size", type=float, help="position size USD")
    a.add_argument("--lev", type=float, help="leverage x")
    a.add_argument("--risk", type=float, help="risk %% of equity")
    a.add_argument("--result", choices=["win", "loss", "be", "open"], default="open")
    a.add_argument("--setup", default="")
    a.add_argument("--reason", default="")
    a.add_argument("--mistake", default="")
    a.add_argument("--notes", default="")
    a.set_defaults(func=cmd_add)

    l = sub.add_parser("list", help="list recent trades")
    l.add_argument("--limit", type=int, default=20)
    l.set_defaults(func=cmd_list)

    an = sub.add_parser("analyze", help="behavioral analysis of recent trades")
    an.add_argument("--limit", type=int, default=100)
    an.add_argument("--send", action="store_true", help="also send to Telegram")
    an.set_defaults(func=cmd_analyze)
    return p


def main(argv=None) -> None:
    _safe_stdout()
    db.init_db()
    args = build_parser().parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
