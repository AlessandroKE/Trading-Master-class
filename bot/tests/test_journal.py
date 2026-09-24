"""Offline tests for the trade journal + behavioral analysis — no network."""
import os
from datetime import datetime, timedelta, timezone

import config.settings as settings
from src.journal import analyze as analyzer
from src.journal import store


def test_r_multiple_long_and_short():
    assert store.compute_r_multiple("LONG", 100, 90, 130) == 3.0
    assert store.compute_r_multiple("SHORT", 100, 110, 80) == 2.0
    assert store.compute_r_multiple("LONG", 100, 100, 130) is None  # zero risk


def test_add_and_recent_roundtrip(tmp_path):
    old = settings.DB_PATH
    settings.DB_PATH = os.path.join(tmp_path, "j.db")
    try:
        from src.storage import db
        db.init_db()
        tid = store.add_trade({"asset": "BTC", "direction": "LONG", "entry": 100,
                               "stop": 90, "exit_price": 130, "result": "win"})
        assert tid >= 1
        rows = store.recent(10)
        assert len(rows) == 1 and rows[0]["asset"] == "BTC"
        assert rows[0]["r_multiple"] == 3.0   # derived on insert
    finally:
        settings.DB_PATH = old


def test_analyze_insufficient_data():
    out = analyzer.analyze([{"result": "win"}])
    assert "need at least" in out


def _t(ts, result, r, lev=3, risk=1.0, mistake=""):
    return {"ts": ts.isoformat(), "asset": "BTC", "direction": "LONG",
            "result": result, "r_multiple": r, "leverage": lev, "risk_pct": risk,
            "mistake": mistake, "setup_type": "x"}


def test_analyze_flags_behaviors():
    base = datetime(2026, 9, 20, 9, 0, tzinfo=timezone.utc)
    trades = [
        _t(base, "loss", -1.0),
        _t(base + timedelta(minutes=30), "loss", -1.5, lev=20),      # revenge + over-lev
        _t(base + timedelta(minutes=45), "loss", -1.2, risk=3.0),    # over-risk
        _t(base + timedelta(minutes=50), "win", 0.5),                # small win
        _t(base + timedelta(minutes=55), "loss", -2.0, mistake="moved stop"),
        _t(base + timedelta(hours=1), "loss", -1.8, mistake="moved stop"),
    ]
    out = analyzer.analyze(trades)
    assert "Overtrading" in out            # 6 trades same day
    assert "revenge" in out.lower()
    assert "Excessive leverage" in out
    assert "Over-risking" in out
    assert "asymmetry" in out.lower()      # avg loss bigger than avg win
    assert "Repeated mistake" in out       # "moved stop" x2


def test_analyze_clean_process():
    base = datetime(2026, 9, 20, 9, 0, tzinfo=timezone.utc)
    trades = [
        _t(base, "win", 2.0),
        _t(base + timedelta(days=1), "loss", -1.0),
        _t(base + timedelta(days=2), "win", 1.8),
    ]
    out = analyzer.analyze(trades)
    assert "None detected" in out
