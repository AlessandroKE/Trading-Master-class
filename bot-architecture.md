# Bot Architecture — Crypto Trader-Helper

**Purpose:** A trader-assistant bot that monitors the **top 20 coins by market cap**, tracks
market structure and derivatives in real time, and delivers **quality-filtered trade setups
twice a day (morning + evening)** plus intraday alerts. It is a **decision-support tool, not
an auto-trader** — execution stays manual.

The bot's *reasoning logic* is defined by `system-prompt.md` in this project. This document
is the *engineering* plan for delivering that logic.

---

## ✅ SELECTED BUILD TARGET — Mode B, Standard tier

- **Mode B (Live monitor):** 24/7 websocket monitoring → twice-daily reports **+** real-time
  intraday alerts (e.g. "BTC swept $80K", "SOL broke $118.84 on volume").
- **Standard cost tier:** small always-on VPS, free exchange market data, no paid on-chain
  data in v1.
- **Estimated cost: ~$5/month for v1** (VPS only; data is free). See cost section.

### Decisions locked
- **Exchange:** **Bybit primary, Binance fallback** (via ccxt). Bybit public market-data works
  from Kenya without account/geo-block; deep futures data. Swappable trivially.
- **Delivery:** Telegram bot (free, phone push, easy).
- **Synthesis (v1): RULE-BASED, no LLM.** The core is fully deterministic — detect structure,
  score against §15, apply the NO-TRADE gate, output entries/stops/TPs/R:R, fill a templated
  report built from the `system-prompt.md` format. **No Claude API needed to start.**
- **Claude API: DEFERRED (optional, later phase).** Adds narrative polish (scenario prose) and
  is genuinely valuable for the §22 JOURNAL behavioral analysis, but is NOT required for v1.
  Trade-off of skipping it: reports read more mechanical/templated; the numbers + discipline
  are identical.

---

## Architecture overview

```
                          ┌─────────────────────────────────┐
                          │        Always-on VPS (Mode B)     │
                          │                                   │
  Exchange WebSockets ───▶│  1. Data layer (live + REST)      │
  (Binance/Bybit/OKX)     │       - OHLCV multi-timeframe     │
                          │       - funding / OI / liq        │
  News/RSS (CryptoPanic)  │       - news + econ calendar      │
                          │                ▼                  │
                          │  2. Analysis engine               │
                          │       - indicators (pandas-ta)    │
                          │       - market-structure detector │
                          │       - quality filter / NO-TRADE │
                          │                ▼                  │
                          │  3. Synthesis (Claude API)        │
                          │       - system-prompt.md as sys   │
                          │       - returns formatted report  │
                          │                ▼                  │
                          │  4. State + journal (SQLite)      │
                          │                ▼                  │
                          │  5. Delivery (Telegram)           │
                          │       - 2x daily reports          │
                          │       - intraday alerts           │
                          │                                   │
                          │  Scheduler: cron (reports) +      │
                          │  event loop (live alerts)         │
                          └─────────────────────────────────┘
```

---

## Components

### 1. Data layer
- **Market / OHLCV:** exchange REST + **WebSockets** via [`ccxt`](https://github.com/ccxt/ccxt)
  (and `ccxt.pro` for streaming). **Free.** Multi-timeframe: 1W/1D/4H/1H/15M.
- **Derivatives:** exchange **futures APIs give funding + OI + long/short ratios free**
  (Binance Futures, Bybit). Covers ~80% of the derivatives analysis. *Optional later:*
  CoinGlass API ($29–79/mo) for aggregated cross-exchange liquidation heatmaps.
- **News/macro:** [CryptoPanic API](https://cryptopanic.com/developers/api/) (free tier) +
  RSS; a scraped/maintained econ-calendar (CPI/PCE/FOMC dates) for event-risk warnings.
- **On-chain:** **excluded from v1** (Glassnode/CryptoQuant = $30–800/mo). Add later if needed.
- **Data integrity (enforce §24 in code):** if a feed is stale/unavailable, emit
  "LIVE DATA UNAVAILABLE" and skip the setup — never fabricate. Timestamp every data point.

### 2. Analysis engine (the real engineering)
- **Indicators:** `pandas` + `pandas-ta` — EMA 20/50/100/200, RSI, MACD, ATR, volume, VWAP.
  (Trivial part.)
- **Market-structure detector (hard part):** swing highs/lows → HH/HL/LH/LL, break-of-
  structure / change-of-character, support/resistance clustering, liquidity zones
  (equal highs/lows, prior D/W highs/lows), sweep/fakeout detection. Expect most dev time
  and iteration here.
- **Quality filter (§15):** score each candidate on structure, trend, S/R, volume, momentum,
  liquidity, OI, funding, liquidations, BTC correlation, macro, news, R:R, entry location.
  **Hard NO-TRADE gate** so the bot stays quiet when nothing qualifies (signal quality > qty).

### 3. Synthesis — RULE-BASED (v1), Claude API deferred
- **v1 (rule-based, no LLM):** a template mirroring the `system-prompt.md` report format
  (regime, top-20 scan, best long/short setups, no-trade zones, execution plan, verdict),
  filled with computed values. Setup classification (Very Strong → No Setup) comes from the
  §15 score thresholds; the NO-TRADE gate keeps it quiet when nothing qualifies. **Cost: $0.**
- **Deferred (Claude API, optional later):** narrative polish + scenario prose, and the §22
  JOURNAL behavioral analysis (where an LLM clearly beats rules). If added: ~$5–15/mo for
  2 reports/day. Not required for v1.

### 4. State + journal (SQLite)
- Track last-alerted levels (dedup), open "watch" setups, and a **journal table** to enable
  the §22 JOURNAL behavioral analysis over time.

### 5. Delivery (Telegram)
- `python-telegram-bot`. Morning + evening reports; intraday alerts on structural events.
- Commands mirroring `system-prompt.md`: `/market`, `/btc`, `/setups`, `/futures`, `/risk`, etc.

### 6. Scheduling (Mode B)
- **Reports:** cron 2x/day (e.g. 07:00 & 19:00 local).
- **Live alerts:** persistent async event loop consuming websockets; alert on confirmed
  structural events with dedup + cooldown to avoid spam.
- Needs an **always-on process** → hence the VPS (not serverless).

---

## Recommended stack

```
Python 3.12
  ccxt / ccxt.pro          Bybit (primary) + Binance (fallback), REST + websocket — free
  pandas + pandas-ta       indicators
  <custom module>          market-structure + liquidity detection
  <template module>        rule-based report synthesis (v1, no LLM)
  SQLite                   state + journal
  python-telegram-bot      delivery + commands
  systemd / supervisor     keep the process alive on the VPS
  cron                     twice-daily report trigger
  anthropic (Claude API)   DEFERRED — optional later (narration + §22 journal)
```

---

## Cost breakdown (Mode B, Standard)

**Compute (always-on required for live monitoring):**
| Option | Cost/mo | Notes |
|---|---|---|
| **Hetzner CX22** | **~$4.5** | Cheapest solid always-on VPS (recommended) |
| Fly.io | $0–5 | Small always-on |
| DigitalOcean / Railway / Render | $5–7 | Easier UX |

**Data + APIs:**
| Item | Cost/mo |
|---|---|
| Exchange market + futures data (ccxt, Bybit/Binance) | **$0** |
| News (CryptoPanic free / RSS) | **$0** |
| Telegram | **$0** |
| Rule-based synthesis (v1) | **$0** |
| *Deferred* Claude API (2 reports/day, top-20) | +$5–15 |
| *Optional* CoinGlass (aggregated liq heatmaps) | +$29–79 |
| *Optional* on-chain (Glassnode/CryptoQuant) | +$30–800 |

### 🎯 Expected total (v1): **~$5/month** — just the VPS
Market/derivatives data is free; v1 synthesis is rule-based (no LLM). Adding Claude later
brings it to ~$10–20/mo.

---

## Hard parts / risks (be honest)
1. **Market-structure detection** is the real work — indicators are trivial; valid
   BOS/CHoCH/liquidity-sweep logic takes iteration.
2. **Data reliability** — handle downtime, rate limits, disagreeing sources; enforce §24 in code.
3. **Signal quality > quantity** — the NO-TRADE gate must be strict or the bot becomes noise.
4. **Not an auto-trader** — v1 uses **read-only API keys**, no trade/withdrawal permissions.
   Execution stays manual. Eliminates the dangerous failure modes.

---

## Build phases
1. ✅ **P1 — Data + indicators:** ccxt (Bybit) top-20 fetch, multi-TF OHLCV, funding/OI, pure-pandas indicators. CLI output. **Done.**
2. ✅ **P2 — Structure + quality filter:** swing/trend/BOS-CHoCH/S-R detection + §15 scoring + NO-TRADE gate + READY/WATCH split. **Done.**
3. **P3 — Rule-based synthesis + delivery:** templated report (system-prompt.md format), twice-daily Telegram.
4. **P4 — Live layer (Mode B):** websocket event loop + intraday alerts + dedup/cooldown.
5. **P5 — Journal:** SQLite journal + behavioral analysis (§22). *Good candidate for adding Claude API here.*

---

## Legal / disclaimer
Outputs are analytical decision-support, **not financial advice**. No auto-execution in v1.
Keep exchange keys read-only.
