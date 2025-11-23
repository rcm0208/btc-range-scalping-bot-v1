from __future__ import annotations

import pytest

from src.core.indicator_engine import IndicatorEngine
from src.utils import Bar


def make_bar(close: float, idx: int) -> Bar:
    return {
        "open": close,
        "high": close,
        "low": close,
        "close": close,
        "volume": 1.0,
        "start_ms": idx * 60_000,
        "end_ms": idx * 60_000 + 60_000,
        "symbol": "BTCUSDT",
        "timeframe": "1m",
    }


def test_rsi_neutral_when_no_moves() -> None:
    engine = IndicatorEngine(rsi_period=7)
    latest = None
    for i in range(20):
        latest = engine.update("1m", make_bar(100.0, i))

    assert latest is not None
    assert latest["rsi"] == pytest.approx(50.0)


def test_rsi_hits_100_when_only_gains() -> None:
    engine = IndicatorEngine(rsi_period=7)
    latest = None
    price = 100.0
    for i in range(20):
        price += 1.0
        latest = engine.update("1m", make_bar(price, i))

    assert latest is not None
    assert latest["rsi"] == pytest.approx(100.0)


def test_rsi_emits_on_warmup_completion() -> None:
    period = 7
    engine = IndicatorEngine(rsi_period=period)
    price = 100.0
    latest = None
    for i in range(period + 1):  # first bar seeds prev_close, then period deltas
        price += 1.0
        latest = engine.update("1m", make_bar(price, i))

    assert latest is not None
    # After period deltas the initial RSI should be emitted (all gains -> 100)
    assert latest["rsi"] == pytest.approx(100.0)
