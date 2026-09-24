"""Live monitor (P4 / Mode B): a polling loop that watches active setups and key levels
between the twice-daily reports and fires intraday alerts (dedup + cooldown).

Polling (REST ~every MONITOR_INTERVAL_SEC) rather than websockets: robust, testable, and
more than adequate for minute-scale alerts. Websockets are a future optimization.

The single process also: refreshes levels/setups every RESCAN_EVERY_SEC, and sends the full
report at REPORT_HOURS — so one always-on process covers reports + alerts (Mode B).
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone

from config import settings
from src.analysis import structure
from src.data.exchange import ExchangeClient
from src.data.universe import to_perp_symbol
from src.indicators import ta
from src.models.types import MarketSnapshot, SetupIdea
from src.monitor.alerts import Alert, AlertStore
from src.delivery import telegram
from src import main as app  # reuse run_scan / deliver_report / safe_stdout

log = logging.getLogger("monitor")


@dataclass
class WatchTarget:
    base: str
    symbol: str
    setup: SetupIdea | None
    support: float | None
    resistance: float | None
    prev_price: float | None = None
    prev_event: str | None = None


def _bucket(x: float | None) -> str:
    return "na" if x is None else f"{x:.4g}"


def _p(x: float | None) -> str:
    """Human-readable price (no scientific notation)."""
    if x is None:
        return "n/a"
    ax = abs(x)
    if ax >= 1000:
        return f"{x:,.0f}"
    if ax >= 1:
        return f"{x:,.2f}"
    return f"{x:.4g}"


def build_targets(snaps: list[MarketSnapshot]) -> list[WatchTarget]:
    """Focused watch set: BTC + coins with a setup, filled by score up to MONITOR_MAX_COINS."""
    chosen: dict[str, MarketSnapshot] = {}
    btc = next((s for s in snaps if s.base == "BTC"), None)
    if btc:
        chosen["BTC"] = btc
    for s in sorted(snaps, key=lambda x: (x.setup is None, -x.score)):
        if len(chosen) >= settings.MONITOR_MAX_COINS:
            break
        chosen.setdefault(s.base, s)

    targets = []
    for s in chosen.values():
        d1 = s.timeframes.get("1d")
        st = d1.structure if d1 else None
        targets.append(WatchTarget(
            base=s.base, symbol=s.symbol, setup=s.setup,
            support=st.nearest_support if st else None,
            resistance=st.nearest_resistance if st else None,
            prev_price=s.price,
        ))
    return targets


def fetch_current(client: ExchangeClient, target: WatchTarget) -> dict | None:
    """Light poll: latest price (15m close), 1h structure event, funding."""
    ohlcv15, _ = client.fetch_ohlcv(target.symbol, "15m", limit=50)
    if not ohlcv15:
        return None
    price = float(ta.to_dataframe(ohlcv15)["close"].iloc[-1])
    event_1h = None
    ohlcv1h, _ = client.fetch_ohlcv(target.symbol, "1h", limit=120)
    if ohlcv1h:
        event_1h = structure.analyze(ta.to_dataframe(ohlcv1h), "1h").last_event
    funding, _ = client.fetch_funding(target.symbol)
    return {"price": price, "event_1h": event_1h, "funding": funding}


def detect_alerts(target: WatchTarget, cur: dict) -> list[Alert]:
    """Pure detection: compare current reading to target's seeded state. No mutation."""
    out: list[Alert] = []
    price = cur.get("price")
    if price is None:
        return out
    b = target.base
    u = target.setup

    # 1. Setup entry reached
    if u is not None and u.entry_low <= price <= u.entry_high:
        out.append(Alert(b, "ENTRY",
                         f"{b} reached {u.direction} entry {_p(u.entry_low)}-{_p(u.entry_high)} "
                         f"(stop {_p(u.stop)}, R:R {u.rr}). Confirm before executing.",
                         key=f"{b}:ENTRY:{_bucket((u.entry_low+u.entry_high)/2)}",
                         severity="high"))

    # 2. Invalidation (price on wrong side of stop)
    if u is not None:
        if (u.direction == "LONG" and price <= u.stop) or \
           (u.direction == "SHORT" and price >= u.stop):
            out.append(Alert(b, "INVALIDATION",
                             f"{b} {u.direction} INVALIDATED - price {_p(price)} hit stop "
                             f"{_p(u.stop)}.",
                             key=f"{b}:INVALIDATION:{_bucket(u.stop)}", severity="high"))

    # 3. Level break (seeded 1D support/resistance)
    buf = settings.LEVEL_BREAK_BUF_PCT / 100.0
    if target.resistance and price > target.resistance * (1 + buf):
        out.append(Alert(b, "LEVEL_BREAK",
                         f"{b} broke ABOVE resistance {_p(target.resistance)} "
                         f"(now {_p(price)}).",
                         key=f"{b}:LEVEL_BREAK:{_bucket(target.resistance)}", severity="high"))
    if target.support and price < target.support * (1 - buf):
        out.append(Alert(b, "LEVEL_BREAK",
                         f"{b} broke BELOW support {_p(target.support)} (now {_p(price)}).",
                         key=f"{b}:LEVEL_BREAK:{_bucket(target.support)}", severity="high"))

    # 4. New 1h structure event
    ev = cur.get("event_1h")
    if ev and ev != target.prev_event:
        out.append(Alert(b, "STRUCTURE",
                         f"{b} 1h {ev.replace('_', ' ')}.",
                         key=f"{b}:STRUCTURE:{ev}"))

    # 5. Rapid move since last cycle
    if target.prev_price:
        move = (price - target.prev_price) / target.prev_price * 100
        if abs(move) >= settings.ALERT_MOVE_PCT:
            direction = "up" if move > 0 else "down"
            out.append(Alert(b, "VOLATILITY",
                             f"{b} moved {move:+.1f}% to {_p(price)} since last check.",
                             key=f"{b}:VOLATILITY:{direction}:{_bucket(price)}"))

    # 6. Funding extreme (crowded positioning)
    fr = cur.get("funding")
    if fr is not None and abs(fr) >= settings.ALERT_FUNDING_ABS:
        side = "longs crowded (positive)" if fr > 0 else "shorts crowded (negative)"
        out.append(Alert(b, "FUNDING",
                         f"{b} funding {fr*100:.3f}% - {side}.",
                         key=f"{b}:FUNDING:{'pos' if fr > 0 else 'neg'}"))
    return out


def _emit(alerts: list[Alert]) -> None:
    if not alerts:
        return
    ts = datetime.now(timezone.utc).strftime("%H:%M UTC")
    lines = [f"[ALERTS] {ts}"] + [f"- ({a.type}) {a.message}" for a in alerts]
    text = "\n".join(lines)
    print("\n" + text)
    if telegram.is_configured():
        telegram.send(text)


def run() -> None:
    app.safe_stdout()
    from src.storage import db
    db.init_db()
    client = ExchangeClient()
    store = AlertStore()

    log.info("Monitor starting - initial scan...")
    snaps = app.run_scan(client)
    app.deliver_report(snaps, to_console=True)
    targets = build_targets(snaps)
    log.info("Watching %d targets: %s", len(targets), ", ".join(t.base for t in targets))

    last_rescan = time.monotonic()
    reports_done: set[str] = set()

    while True:
        cycle_alerts: list[Alert] = []
        for t in targets:
            try:
                cur = fetch_current(client, t)
                if not cur:
                    continue
                cycle_alerts.extend(detect_alerts(t, cur))
                t.prev_price = cur["price"]
                if cur.get("event_1h"):
                    t.prev_event = cur["event_1h"]
            except Exception as exc:  # noqa: BLE001
                log.warning("monitor cycle failed for %s: %s", t.base, exc)

        _emit(store.filter_new(cycle_alerts))

        # Scheduled full report at REPORT_HOURS (once per hour-slot)
        now = datetime.now(timezone.utc)
        slot = now.strftime("%Y-%m-%d-%H")
        if now.hour in settings.REPORT_HOURS and slot not in reports_done:
            log.info("Scheduled report (%s)...", settings.session_label())
            snaps = app.run_scan(client)
            app.deliver_report(snaps, to_console=True)
            targets = build_targets(snaps)
            reports_done.add(slot)
            last_rescan = time.monotonic()

        # Periodic rescan to refresh levels/setups
        if time.monotonic() - last_rescan >= settings.RESCAN_EVERY_SEC:
            log.info("Periodic rescan - refreshing levels/setups...")
            snaps = app.run_scan(client)
            targets = build_targets(snaps)
            last_rescan = time.monotonic()

        time.sleep(settings.MONITOR_INTERVAL_SEC)


if __name__ == "__main__":
    run()
