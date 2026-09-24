# Crypto Trader-Helper Bot

Decision-support bot: monitors the top-20 coins, tracks market structure + derivatives,
and delivers quality-filtered trade setups. **Not an auto-trader** — execution is manual,
API keys are read-only.

See `../bot-architecture.md` for the full plan and `../system-prompt.md` for the analyst logic.

## Phase 1 (this scaffold)
Fetches the current **top-20 by market cap** (CoinGecko, free), pulls **multi-timeframe OHLCV +
funding + open interest** from **Bybit** (Binance fallback) via `ccxt`, computes indicators, and
prints a scan table to the console. No structure detection or delivery yet — that's P2/P3.

## Quick start (local)

```bash
cd bot
python -m venv .venv
# Windows PowerShell:  .venv\Scripts\Activate.ps1
# bash:                source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # edit if you add exchange keys (optional for public data)
python -m src.main
```

## Quick start (Docker)

```bash
cd bot
docker compose up --build
```

The SQLite DB persists in `bot/data/` (mounted as a volume).

## Notes
- **No exchange account is needed** for P1 — public market data works without keys.
- Indicators are computed in pure `pandas` (no `pandas-ta`) to avoid the `numpy>=2` breakage.
- DB is **SQLite** for v1 (see architecture doc). A Postgres service is stubbed in
  `docker-compose.yml` for when a UI/multi-user need arrives.
