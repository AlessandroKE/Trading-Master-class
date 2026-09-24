"""ccxt wrapper: Bybit primary, Binance fallback. Fetches OHLCV + derivatives.

Only public market-data endpoints are used in P1 (no account required). If keys are
present they are loaded read-only."""
from __future__ import annotations

import logging

import ccxt

from config import settings

log = logging.getLogger(__name__)


class ExchangeClient:
    def __init__(self) -> None:
        self._clients: dict[str, ccxt.Exchange] = {}
        self.order = [settings.PRIMARY_EXCHANGE, settings.FALLBACK_EXCHANGE]

    def has_perp(self, symbol: str) -> bool:
        """True if any configured exchange lists this linear-perp symbol."""
        for name in self.order:
            try:
                markets = self._client(name).load_markets()
                if symbol in markets:
                    return True
            except Exception as exc:  # noqa: BLE001
                log.debug("%s load_markets failed: %s", name, exc)
        return False

    def _client(self, name: str) -> ccxt.Exchange:
        if name not in self._clients:
            keys = settings.EXCHANGE_KEYS.get(name, {})
            klass = getattr(ccxt, name)
            self._clients[name] = klass(
                {
                    "apiKey": keys.get("apiKey"),
                    "secret": keys.get("secret"),
                    "enableRateLimit": True,
                    "options": {"defaultType": "swap"},  # linear perps
                }
            )
        return self._clients[name]

    # --- OHLCV --------------------------------------------------------------
    def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int | None = None):
        """Return list of [ts, open, high, low, close, volume] or None on failure.
        Tries primary then fallback."""
        limit = limit or settings.OHLCV_LIMIT
        for name in self.order:
            try:
                return self._client(name).fetch_ohlcv(symbol, timeframe=timeframe, limit=limit), name
            except Exception as exc:  # noqa: BLE001
                log.debug("%s OHLCV %s %s failed: %s", name, symbol, timeframe, exc)
        return None, None

    # --- Derivatives --------------------------------------------------------
    def fetch_funding(self, symbol: str):
        for name in self.order:
            try:
                fr = self._client(name).fetch_funding_rate(symbol)
                return fr.get("fundingRate"), name
            except Exception as exc:  # noqa: BLE001
                log.debug("%s funding %s failed: %s", name, symbol, exc)
        return None, None

    def fetch_open_interest(self, symbol: str):
        for name in self.order:
            try:
                oi = self._client(name).fetch_open_interest(symbol)
                return (
                    oi.get("openInterestAmount"),
                    oi.get("openInterestValue"),
                    name,
                )
            except Exception as exc:  # noqa: BLE001
                log.debug("%s OI %s failed: %s", name, symbol, exc)
        return None, None, None
