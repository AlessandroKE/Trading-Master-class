"""Telegram delivery via the Bot API (uses `requests` — no extra dependency).

The whole report is sent inside <pre> blocks (monospace) so tables align on mobile and we
avoid Markdown-escaping pitfalls. Long reports are split across messages (4096-char limit).
No-op (logs a warning) when the bot isn't configured, so local runs still work."""
from __future__ import annotations

import html
import logging

import requests

from config import settings

log = logging.getLogger(__name__)

API = "https://api.telegram.org/bot{token}/sendMessage"
# Telegram hard limit is 4096 chars/message; leave headroom for the <pre> wrapper.
CHUNK = 3500


def is_configured() -> bool:
    return bool(settings.TELEGRAM_BOT_TOKEN and settings.TELEGRAM_CHAT_ID)


def _chunk_lines(text: str, limit: int = CHUNK) -> list[str]:
    chunks: list[str] = []
    buf: list[str] = []
    size = 0
    for line in text.split("\n"):
        # +1 for the newline; hard-split any single monster line
        while len(line) > limit:
            chunks.append(line[:limit])
            line = line[limit:]
        if size + len(line) + 1 > limit and buf:
            chunks.append("\n".join(buf))
            buf, size = [], 0
        buf.append(line)
        size += len(line) + 1
    if buf:
        chunks.append("\n".join(buf))
    return chunks


def send(text: str) -> bool:
    """Send a report to the configured chat. Returns True if all chunks sent OK."""
    if not is_configured():
        log.warning("Telegram not configured (TELEGRAM_BOT_TOKEN/CHAT_ID) - skipping send.")
        return False

    url = API.format(token=settings.TELEGRAM_BOT_TOKEN)
    ok = True
    for i, chunk in enumerate(_chunk_lines(text)):
        payload = {
            "chat_id": settings.TELEGRAM_CHAT_ID,
            "text": f"<pre>{html.escape(chunk)}</pre>",
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        try:
            r = requests.post(url, json=payload, timeout=settings.HTTP_TIMEOUT)
            if r.status_code != 200:
                log.warning("Telegram send failed (chunk %d): %s %s",
                            i, r.status_code, r.text[:200])
                ok = False
        except Exception as exc:  # noqa: BLE001
            log.warning("Telegram send error (chunk %d): %s", i, exc)
            ok = False
    return ok
