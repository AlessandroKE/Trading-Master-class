"""SQLite storage (v1 DB choice). Persists scan snapshots and a trade journal.

Why SQLite: zero-ops, single file, perfect for a single-process bot. The file lives on a
mounted Docker volume so it survives restarts. When a UI / concurrent access arrives,
switch to Postgres (compose service is stubbed) — the schema below ports directly."""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone

from config import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS snapshots (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          TEXT NOT NULL,
    base        TEXT NOT NULL,
    symbol      TEXT NOT NULL,
    price       REAL,
    change_24h  REAL,
    funding     REAL,
    oi_usd      REAL,
    payload     TEXT               -- full MarketSnapshot as JSON
);
CREATE INDEX IF NOT EXISTS idx_snapshots_base_ts ON snapshots(base, ts);

CREATE TABLE IF NOT EXISTS journal (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          TEXT NOT NULL,
    asset       TEXT NOT NULL,
    direction   TEXT,              -- LONG / SHORT
    entry       REAL,
    stop        REAL,
    tp          REAL,
    size_usd    REAL,
    leverage    REAL,
    risk_pct    REAL,
    result      TEXT,              -- win / loss / be / open
    setup_type  TEXT,
    reason      TEXT,
    mistake     TEXT,
    notes       TEXT
);
"""


def connect() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(settings.DB_PATH) or ".", exist_ok=True)
    conn = sqlite3.connect(settings.DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = connect()
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


def save_snapshot(snap) -> None:
    """Persist a MarketSnapshot (dataclass) as one row + JSON payload."""
    conn = connect()
    try:
        conn.execute(
            "INSERT INTO snapshots (ts, base, symbol, price, change_24h, funding, oi_usd, payload)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                snap.ts or datetime.now(timezone.utc).isoformat(),
                snap.base,
                snap.symbol,
                snap.price,
                snap.change_24h_pct,
                snap.derivatives.funding_rate,
                snap.derivatives.oi_notional_usd,
                json.dumps(_snap_to_dict(snap), default=str),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _snap_to_dict(snap) -> dict:
    from dataclasses import asdict
    return asdict(snap)
