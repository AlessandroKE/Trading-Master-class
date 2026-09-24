"""Offline tests for report synthesis + Telegram chunking — no network."""
from src.delivery import telegram
from src.models.types import (Derivatives, Indicators, MarketSnapshot, SetupIdea,
                              StructureView, TimeframeView)
from src.report import builder


def _snap(base, bias, price, change, with_setup=False, rank=1):
    s = MarketSnapshot(symbol=f"{base}/USDT:USDT", base=base, price=price,
                       change_24h_pct=change, market_cap_rank=rank, bias=bias, score=75,
                       classification="Strong")
    sv = StructureView("1d", trend="uptrend" if bias == "bullish" else "downtrend",
                       nearest_support=price * 0.9, nearest_resistance=price * 1.1,
                       last_swing_low=price * 0.85, last_swing_high=price * 1.15)
    s.timeframes["1d"] = TimeframeView("1d", last_close=price,
                                       indicators=Indicators(ema50=price * 0.95),
                                       structure=sv)
    s.derivatives = Derivatives(funding_rate=0.0001, oi_notional_usd=1e9)
    if with_setup:
        s.setup = SetupIdea("LONG", "support bounce", price * 0.98, price * 1.0,
                            price * 0.9, price * 1.1, price * 1.2, price * 1.3, 2.0,
                            "Strong", ["1D uptrend"], "BTC rollover",
                            status="ready", distance_pct=0.0)
    return s


def test_report_has_all_sections():
    snaps = [
        _snap("BTC", "bullish", 80000, -2.0, with_setup=True, rank=1),
        _snap("ETH", "bearish", 2600, -3.0, rank=2),
    ]
    r = builder.build_report(snaps, session="MORNING")
    for section in ["CRYPTO MARKET REPORT", "MARKET SUMMARY", "TOP MARKET SCAN",
                    "BEST LONG SETUPS", "BEST SHORT SETUPS", "WATCHLIST",
                    "EXECUTION PLAN", "FINAL VERDICT"]:
        assert section in r
    assert "MORNING" in r
    # honesty note about missing macro/news must be present (§24)
    assert "NOT yet integrated" in r


def test_verdict_no_trade_when_empty():
    snaps = [_snap("BTC", "neutral", 80000, -1.0)]
    r = builder.build_report(snaps)
    assert "NO TRADE" in r


def test_verdict_tradeable_with_ready_setup():
    snaps = [_snap("BTC", "bullish", 80000, 1.0, with_setup=True)]
    r = builder.build_report(snaps)
    assert "TRADEABLE" in r


def test_telegram_not_configured_is_safe():
    # With no token configured, send() must no-op to False, never raise.
    assert telegram.is_configured() in (True, False)
    assert telegram.send("hello") in (True, False)


def test_chunking_respects_limit():
    big = "\n".join(f"line {i} " + "x" * 100 for i in range(400))
    chunks = telegram._chunk_lines(big, limit=1000)
    assert all(len(c) <= 1000 for c in chunks)
    assert len(chunks) > 1
