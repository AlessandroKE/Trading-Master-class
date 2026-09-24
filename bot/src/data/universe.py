"""Resolve the current top-N coins by market cap (CoinGecko, free) and map to
exchange perp symbols. Excludes stablecoins/wrapped assets."""
from __future__ import annotations

import logging

import requests

from config import settings

log = logging.getLogger(__name__)


def get_top_symbols(pool: int | None = None) -> list[dict]:
    """Return up to `pool` candidate coins (top by market cap, stables excluded).

    The caller filters these down to TOP_N with a valid perp market. Uses CoinGecko's free
    markets endpoint; falls back to a static list if unreachable (data-integrity: we flag
    the fallback rather than fabricate ranks)."""
    pool = pool or settings.CANDIDATE_POOL
    try:
        resp = requests.get(settings.COINGECKO_MARKETS_URL, timeout=settings.HTTP_TIMEOUT)
        resp.raise_for_status()
        rows = resp.json()
    except Exception as exc:  # noqa: BLE001
        log.warning("CoinGecko unavailable (%s) - using static fallback universe.", exc)
        return _static_fallback(settings.TOP_N)

    out: list[dict] = []
    for row in rows:
        base = (row.get("symbol") or "").upper()
        if not base or base in settings.EXCLUDE_SYMBOLS:
            continue
        out.append(
            {
                "base": base,
                "rank": row.get("market_cap_rank"),
                "cg_price": row.get("current_price"),
                "cg_change_24h": row.get("price_change_percentage_24h"),
            }
        )
        if len(out) >= pool:
            break
    return out


def to_perp_symbol(base: str, quote: str | None = None) -> str:
    """ccxt unified linear-perp symbol, e.g. 'BTC/USDT:USDT'."""
    quote = quote or settings.QUOTE
    return f"{base}/{quote}:{quote}"


def _static_fallback(n: int) -> list[dict]:
    """Last-resort universe if the ranking API is down. Marked so callers know it's stale."""
    bases = [
        "BTC", "ETH", "BNB", "SOL", "XRP", "ADA", "DOGE", "TRX", "AVAX", "LINK",
        "TON", "DOT", "MATIC", "LTC", "BCH", "NEAR", "APT", "ICP", "SUI", "ETC",
    ]
    return [{"base": b, "rank": None, "cg_price": None, "cg_change_24h": None,
             "stale_fallback": True} for b in bases[:n]]
