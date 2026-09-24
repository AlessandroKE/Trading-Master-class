"""Alert types + a SQLite-backed dedup/cooldown store (P4).

Cooldown is persisted so a process restart doesn't re-spam alerts that already fired.
The dedup key encodes (base, type, level-bucket) so distinct events still get through.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from config import settings
from src.storage import db


@dataclass
class Alert:
    base: str
    type: str            # ENTRY / INVALIDATION / LEVEL_BREAK / STRUCTURE / VOLATILITY / FUNDING
    message: str
    key: str             # dedup key
    severity: str = "info"   # info / high


def _now() -> datetime:
    return datetime.now(timezone.utc)


class AlertStore:
    """Tracks last-fired times to enforce per-type cooldowns."""

    def should_fire(self, alert: Alert, now: datetime | None = None) -> bool:
        now = now or _now()
        cooldown = settings.ALERT_COOLDOWN_SEC.get(alert.type, 1800)
        conn = db.connect()
        try:
            row = conn.execute("SELECT ts FROM alerts_fired WHERE key = ?",
                               (alert.key,)).fetchone()
            if row is not None:
                last = datetime.fromisoformat(row["ts"])
                if (now - last).total_seconds() < cooldown:
                    return False
            return True
        finally:
            conn.close()

    def mark_fired(self, alert: Alert, now: datetime | None = None) -> None:
        now = now or _now()
        conn = db.connect()
        try:
            conn.execute(
                "INSERT INTO alerts_fired (key, ts) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET ts = excluded.ts",
                (alert.key, now.isoformat()),
            )
            conn.commit()
        finally:
            conn.close()

    def filter_new(self, alerts: list[Alert], now: datetime | None = None) -> list[Alert]:
        """Return only alerts past cooldown, marking them fired."""
        now = now or _now()
        out: list[Alert] = []
        for a in alerts:
            if self.should_fire(a, now):
                self.mark_fired(a, now)
                out.append(a)
        return out
