"""P1 entrypoint: scan the top-N universe and print a market table.

Pipeline: universe (CoinGecko) -> per coin OHLCV+derivatives (Bybit/Binance via ccxt)
-> indicators (pandas) -> console table + persist to SQLite.

No structure detection, scoring, or delivery yet (that's P2/P3)."""
from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone

from tabulate import tabulate

from config import settings
from src.analysis import scoring, structure
from src.data.exchange import ExchangeClient
from src.data.universe import get_top_symbols, to_perp_symbol
from src.delivery import telegram
from src.indicators import ta
from src.models.types import Derivatives, MarketSnapshot, TimeframeView
from src.report import builder
from src.storage import db

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("trader-helper")


def scan_symbol(client: ExchangeClient, coin: dict) -> MarketSnapshot:
    base = coin["base"]
    symbol = to_perp_symbol(base)
    snap = MarketSnapshot(
        symbol=symbol,
        base=base,
        market_cap_rank=coin.get("rank"),
        change_24h_pct=coin.get("cg_change_24h"),
        ts=datetime.now(timezone.utc).isoformat(),
    )

    for tf in settings.TIMEFRAMES:
        ohlcv, ex = client.fetch_ohlcv(symbol, tf)
        if not ohlcv:
            snap.errors.append(f"ohlcv:{tf}")
            continue
        snap.exchange = snap.exchange or ex
        df = ta.to_dataframe(ohlcv)
        view = TimeframeView(timeframe=tf, last_close=float(df["close"].iloc[-1]))
        view.indicators = ta.compute(df)
        # Structure detection on HTF + intermediate only (per multi-timeframe model)
        if tf in ("1d", "4h"):
            view.structure = structure.analyze(df, tf)
        snap.timeframes[tf] = view

    # Price from the fastest timeframe we got
    for tf in reversed(settings.TIMEFRAMES):
        if tf in snap.timeframes:
            snap.price = snap.timeframes[tf].last_close
            break

    # Derivatives
    funding, fex = client.fetch_funding(symbol)
    oi_amt, oi_val, oiex = client.fetch_open_interest(symbol)
    # Bybit returns OI amount (in base) but not USD value -> derive it from price.
    if oi_val is None and oi_amt is not None and snap.price:
        oi_val = oi_amt * snap.price
    snap.derivatives = Derivatives(
        funding_rate=funding,
        open_interest=oi_amt,
        oi_notional_usd=oi_val,
        source=fex or oiex,
    )
    scoring.evaluate(snap)   # P2: bias + quality score + candidate setup (NO-TRADE gate)
    return snap


def build_row(snap: MarketSnapshot) -> list:
    d1 = snap.timeframes.get("1d")
    h4 = snap.timeframes.get("4h")

    def trend(view: TimeframeView | None) -> str:
        if not view or view.last_close is None or view.indicators.ema50 is None:
            return "-"
        return "up" if view.last_close >= view.indicators.ema50 else "down"

    rsi_1d = d1.indicators.rsi14 if d1 else None
    funding = snap.derivatives.funding_rate
    struct_1d = d1.structure.trend if (d1 and d1.structure) else "-"
    return [
        snap.market_cap_rank if snap.market_cap_rank is not None else "?",
        snap.base,
        f"{snap.price:,.4g}" if snap.price else "-",
        f"{snap.change_24h_pct:+.1f}%" if snap.change_24h_pct is not None else "-",
        struct_1d,
        trend(h4),
        f"{rsi_1d:.0f}" if rsi_1d is not None else "-",
        f"{funding*100:.4f}%" if funding is not None else "-",
        f"{snap.derivatives.oi_notional_usd/1e6:,.0f}M"
        if snap.derivatives.oi_notional_usd else "-",
        snap.bias,
        f"{snap.score} {snap.classification}",
    ]


def _print_idea(s: MarketSnapshot) -> None:
    u = s.setup
    dist = f"{u.distance_pct:+.1f}% to entry" if u.status == "watch" else "AT ENTRY"
    print(f"\n{s.base}/USDT  -  {u.direction}  [{u.confidence}, score {s.score}]  "
          f"({u.setup_type})  | {dist}")
    print(f"  Entry {u.entry_low:,.4g}–{u.entry_high:,.4g} | Stop {u.stop:,.4g} | "
          f"TP1 {u.tp1:,.4g} / TP2 {u.tp2:,.4g} / TP3 {u.tp3:,.4g} | R:R {u.rr}")
    print(f"  Why: {'; '.join(u.reasons)}")
    print(f"  Main risk: {u.main_risk}")


def print_setups(snaps: list[MarketSnapshot]) -> None:
    """Split gate-passing ideas into READY (price at entry) vs WATCH (wait for level)."""
    ideas = [s for s in snaps if s.setup is not None]
    ideas.sort(key=lambda s: s.score, reverse=True)
    ready = [s for s in ideas if s.setup.status == "ready"]
    watch = [s for s in ideas if s.setup.status == "watch"]

    print("\n=== [ACTIONABLE SETUPS] price at/near entry, gate passed ===")
    if not ready:
        print("NO ACTIONABLE SETUP RIGHT NOW - nothing is at a tradeable entry. WAIT.")
    else:
        for s in ready:
            _print_idea(s)

    if watch:
        print("\n=== [WATCHLIST] structurally aligned, waiting for price to reach entry ===")
        for s in watch:
            _print_idea(s)

    print("\n! Candidates from structure + derivatives only. News/macro/BTC-correlation "
          "checks come in later phases. Confirm before entry.")


def main() -> None:
    # Make console output robust on Windows (cp1252) terminals.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

    db.init_db()
    client = ExchangeClient()

    candidates = get_top_symbols()
    # Keep only top-cap coins that actually have a perp market; take TOP_N of those.
    universe = []
    for coin in candidates:
        if client.has_perp(to_perp_symbol(coin["base"])):
            universe.append(coin)
        if len(universe) >= settings.TOP_N:
            break
    log.info("Universe: %d coins (top by market cap w/ perp market, stables excluded)",
             len(universe))

    rows = []
    snaps: list[MarketSnapshot] = []
    for coin in universe:
        try:
            snap = scan_symbol(client, coin)
            db.save_snapshot(snap)
            snaps.append(snap)
            rows.append(build_row(snap))
        except Exception as exc:  # noqa: BLE001
            log.warning("scan failed for %s: %s", coin.get("base"), exc)

    headers = ["#", "Coin", "Price", "24h", "1D Struct", "4H", "RSI(1D)",
               "Funding", "OI", "Bias", "Score"]
    print("\n=== TOP-%d SCAN  (%s UTC) ===" % (
        len(universe), datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")))
    print(tabulate(rows, headers=headers, tablefmt="github"))
    print_setups(snaps)

    # --- P3: synthesize the daily report and deliver ---
    report = builder.build_report(snaps, session=settings.session_label())
    print("\n" + "#" * 70)
    print(report)
    if telegram.is_configured():
        sent = telegram.send(report)
        log.info("Telegram delivery: %s", "sent" if sent else "FAILED")
    else:
        log.info("Telegram not configured - report printed to console only.")


if __name__ == "__main__":
    main()
