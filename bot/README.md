# Crypto Trader-Helper Bot

Decision-support bot: monitors the top-20 coins, tracks market structure + derivatives,
and delivers quality-filtered trade setups. **Not an auto-trader** — execution is manual,
API keys are read-only.

See `../bot-architecture.md` for the full plan and `../system-prompt.md` for the analyst logic.

## Status: P1–P5 done (core build complete)
- **P1** — top-20 by market cap (CoinGecko), multi-timeframe OHLCV + funding + OI from Bybit
  (Binance fallback) via `ccxt`, indicators.
- **P2** — market-structure detection (swings, trend, BOS/CHoCH, S/R), §15 quality scoring,
  NO-TRADE gate, READY vs WATCH split.
- **P3** — rule-based daily-report synthesis (system-prompt.md format) + Telegram delivery.
- **P4** — live monitor (Mode B): polling loop with intraday alerts (entry reached,
  invalidation, level break, 1h BOS/CHoCH, volatility, funding extreme) + dedup/cooldown;
  also fires the scheduled report at REPORT_HOURS.
- **P5** — trade journal + behavioral analysis (§22): log trades, then flag overtrading,
  revenge trading, excessive leverage, over-risking, win/loss R asymmetry, repeated mistakes.

## Trade journal (§22)
```bash
python -m src.journal add --asset BTC --dir LONG --entry 83000 --stop 81000 \
    --exit 88000 --size 200 --lev 3 --risk 1 --result win --setup "support bounce"
python -m src.journal list
python -m src.journal analyze [--send]     # behavioral analysis (--send to Telegram)
```
R-multiple is derived from entry/stop/exit automatically.

## Two ways to run
- **One-shot report** (cron-friendly): `python -m src.main` — prints the full
  **CRYPTO MARKET REPORT** and sends it if Telegram is configured, then exits.
- **Always-on monitor** (Mode B): `python -m src.monitor.engine` — sends an initial report,
  then polls a focused watch set every `MONITOR_INTERVAL_SEC` for intraday alerts and sends
  the full report at `REPORT_HOURS` (07:00 & 19:00 UTC). This is the Docker default.

## Deploy (Mode B, always-on)
```bash
cd bot && docker compose up -d --build      # runs the monitor, restarts on reboot
```
The report auto-labels MORNING (UTC < 12:00) or EVENING.

### Alternative: cron one-shots (no always-on process)
```
0 7,19 * * *  cd /path/to/bot && /path/to/.venv/bin/python -m src.main >> logs/run.log 2>&1
```
Windows: a Task Scheduler daily task with two triggers (07:00, 19:00) running
`python -m src.main` in the `bot` dir.

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
