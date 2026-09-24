"""Offline tests for monitor alert detection + cooldown store — no network."""
import os
import tempfile
from datetime import datetime, timedelta, timezone

import config.settings as settings
from src.models.types import SetupIdea
from src.monitor.alerts import Alert, AlertStore
from src.monitor.engine import WatchTarget, detect_alerts


def _target(setup=None, support=None, resistance=None, prev_price=100.0, prev_event=None):
    return WatchTarget(base="TEST", symbol="TEST/USDT:USDT", setup=setup,
                       support=support, resistance=resistance,
                       prev_price=prev_price, prev_event=prev_event)


def _long_setup():
    return SetupIdea("LONG", "support bounce", 98, 100, 95, 110, 115, 120, 2.0,
                     "Strong", ["x"], "risk", status="watch", distance_pct=3.0)


def test_entry_alert_fires_in_zone():
    t = _target(setup=_long_setup())
    alerts = detect_alerts(t, {"price": 99, "event_1h": None, "funding": None})
    assert any(a.type == "ENTRY" for a in alerts)


def test_invalidation_when_stop_breached():
    t = _target(setup=_long_setup())
    alerts = detect_alerts(t, {"price": 94, "event_1h": None, "funding": None})
    assert any(a.type == "INVALIDATION" for a in alerts)


def test_level_break_above_resistance():
    t = _target(resistance=100.0, prev_price=99.0)
    alerts = detect_alerts(t, {"price": 101.0, "event_1h": None, "funding": None})
    assert any(a.type == "LEVEL_BREAK" for a in alerts)


def test_structure_event_only_when_changed():
    t = _target(prev_event="BOS_up")
    same = detect_alerts(t, {"price": 100, "event_1h": "BOS_up", "funding": None})
    assert not any(a.type == "STRUCTURE" for a in same)
    changed = detect_alerts(t, {"price": 100, "event_1h": "CHoCH_down", "funding": None})
    assert any(a.type == "STRUCTURE" for a in changed)


def test_volatility_and_funding():
    t = _target(prev_price=100.0)
    alerts = detect_alerts(t, {"price": 102.0, "event_1h": None, "funding": 0.001})
    types = {a.type for a in alerts}
    assert "VOLATILITY" in types and "FUNDING" in types


def test_no_alert_on_quiet_cycle():
    t = _target(prev_price=100.0)
    alerts = detect_alerts(t, {"price": 100.2, "event_1h": None, "funding": 0.0001})
    assert alerts == []


def test_cooldown_store(tmp_path):
    # point DB at a temp file
    old = settings.DB_PATH
    settings.DB_PATH = os.path.join(tmp_path, "t.db")
    try:
        from src.storage import db
        db.init_db()
        store = AlertStore()
        a = Alert("BTC", "LEVEL_BREAK", "msg", key="BTC:LEVEL_BREAK:100")
        now = datetime.now(timezone.utc)
        assert store.should_fire(a, now) is True
        store.mark_fired(a, now)
        # within cooldown -> blocked
        assert store.should_fire(a, now + timedelta(seconds=10)) is False
        # after cooldown -> allowed
        cd = settings.ALERT_COOLDOWN_SEC["LEVEL_BREAK"]
        assert store.should_fire(a, now + timedelta(seconds=cd + 1)) is True
    finally:
        settings.DB_PATH = old
