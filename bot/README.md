# Crypto Trader-Helper Bot

Decision-support bot: monitors the top-20 coins, tracks market structure + derivatives,
and delivers quality-filtered trade setups. **Not an auto-trader** — execution is manual,
API keys are read-only.

See `../bot-architecture.md` for the full plan and `../system-prompt.md` for the analyst logic.

## Status: P1 + P2 + P3 done
- **P1** — top-20 by market cap (CoinGecko), multi-timeframe OHLCV + funding + OI from Bybit
  (Binance fallback) via `ccxt`, indicators.
- **P2** — market-structure detection (swings, trend, BOS/CHoCH, S/R), §15 quality scoring,
  NO-TRADE gate, READY vs WATCH split.
- **P3** — rule-based daily-report synthesis (system-prompt.md format) + Telegram delivery.

Running `python -m src.main` now prints a full **CRYPTO MARKET REPORT** and, if Telegram is
configured, sends it to your chat.

## Scheduling (twice daily)
`main` runs one scan+report and exits. Trigger it morning and evening:

- **Linux/VPS (cron):**
  ```
  0 7,19 * * *  cd /path/to/bot && /path/to/.venv/bin/python -m src.main >> logs/run.log 2>&1
  ```
  or with Docker: `0 7,19 * * *  cd /path/to/bot && docker compose run --rm bot`
- **Windows (Task Scheduler):** create a Daily task with two triggers (07:00, 19:00) running
  `python -m src.main` in the `bot` dir.

The report auto-labels MORNING (UTC < 12:00) or EVENING.

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
