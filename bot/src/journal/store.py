"""Journal storage (P5): record completed trades and read them back for analysis (§22)."""
from __future__ import annotations

from datetime import datetime, timezone

from src.storage import db

FIELDS = ["ts", "asset", "direction", "entry", "stop", "tp", "exit_price", "r_multiple",
          "size_usd", "leverage", "risk_pct", "result", "setup_type", "reason",
          "mistake", "notes"]


def compute_r_multiple(direction: str, entry, stop, exit_price) -> float | None:
    """Realized R = reward/risk relative to the planned stop distance."""
    try:
        risk = abs(entry - stop)
        if risk == 0:
            return None
        if (direction or "").upper() == "LONG":
            return round((exit_price - entry) / risk, 2)
        return round((entry - exit_price) / risk, 2)
    except (TypeError, ValueError):
        return None


def add_trade(trade: dict) -> int:
    """Insert a completed trade. Fills ts and derives r_multiple if omitted."""
    t = {k: trade.get(k) for k in FIELDS}
    t["ts"] = t["ts"] or datetime.now(timezone.utc).isoformat()
    if t["r_multiple"] is None and t.get("exit_price") is not None:
        t["r_multiple"] = compute_r_multiple(t["direction"], t["entry"], t["stop"],
                                             t["exit_price"])
    conn = db.connect()
    try:
        cur = conn.execute(
            f"INSERT INTO journal ({','.join(FIELDS)}) "
            f"VALUES ({','.join('?' for _ in FIELDS)})",
            [t[k] for k in FIELDS],
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def recent(limit: int = 100) -> list[dict]:
    conn = db.connect()
    try:
        rows = conn.execute(
            "SELECT * FROM journal ORDER BY ts DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows][::-1]  # oldest-first for analysis
    finally:
        conn.close()
