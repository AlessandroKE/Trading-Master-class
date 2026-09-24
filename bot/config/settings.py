"""Central configuration. Reads from environment (.env) with sensible defaults."""
from __future__ import annotations

import os
from dotenv import load_dotenv

load_dotenv()

# --- Universe ---
TOP_N: int = int(os.getenv("TOP_N", "20"))
QUOTE: str = os.getenv("QUOTE", "USDT")

# Stablecoins / wrapped / pegged assets excluded from directional analysis.
EXCLUDE_SYMBOLS: set[str] = {
    "USDT", "USDC", "DAI", "TUSD", "FDUSD", "USDE", "PYUSD", "BUSD", "USDS", "USD1",
    "WBTC", "WETH", "WEETH", "STETH", "WSTETH", "WBETH",
}

# How many market-cap candidates to pull before filtering down to TOP_N with valid perps.
# (Some top-cap assets are RWAs/exchange tokens with no perp market, e.g. FIGR_HELOC, LEO.)
CANDIDATE_POOL: int = 50

# --- Timeframes (per system-prompt.md multi-timeframe model) ---
# HTF -> intermediate -> entry
TIMEFRAMES: list[str] = ["1w", "1d", "4h", "1h", "15m"]
OHLCV_LIMIT: int = 300  # candles per timeframe (enough for EMA200 + structure)

# --- Exchanges (primary, then fallback) ---
PRIMARY_EXCHANGE: str = os.getenv("PRIMARY_EXCHANGE", "bybit")
FALLBACK_EXCHANGE: str = os.getenv("FALLBACK_EXCHANGE", "binance")

EXCHANGE_KEYS: dict[str, dict[str, str | None]] = {
    "bybit": {
        "apiKey": os.getenv("BYBIT_API_KEY") or None,
        "secret": os.getenv("BYBIT_API_SECRET") or None,
    },
    "binance": {
        "apiKey": os.getenv("BINANCE_API_KEY") or None,
        "secret": os.getenv("BINANCE_API_SECRET") or None,
    },
}

# --- Storage ---
DB_PATH: str = os.getenv("DB_PATH", "data/trader.db")

# --- Delivery (Telegram) ---
TELEGRAM_BOT_TOKEN: str | None = os.getenv("TELEGRAM_BOT_TOKEN") or None
TELEGRAM_CHAT_ID: str | None = os.getenv("TELEGRAM_CHAT_ID") or None

# Session label auto-picked from UTC hour if not provided (morning/evening report).
def session_label() -> str:
    from datetime import datetime, timezone
    hour = datetime.now(timezone.utc).hour
    return "MORNING" if hour < 12 else "EVENING"

# --- Data source for market-cap ranking (free, no key) ---
COINGECKO_MARKETS_URL: str = (
    "https://api.coingecko.com/api/v3/coins/markets"
    "?vs_currency=usd&order=market_cap_desc&per_page=50&page=1"
)
HTTP_TIMEOUT: int = 20
