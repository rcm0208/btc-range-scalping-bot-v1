from __future__ import annotations

from typing import cast

import pytest

from src.core.indicator_engine import IndicatorEngine
from src.utils import Bar, Timeframe


def make_bar(i: int) -> Bar:
    base = 100.0 + i * 0.1
    return {
        "open": base,
        "high": base + 0.3,
        "low": base - 0.3,
        "close": base + 0.05,
        "volume": 10.0 + i,
        "start_ms": i * 60_000,
        "end_ms": i * 60_000 + 60_000,
        "symbol": "BTCUSDT",
        "timeframe": "1m",
    }


def test_indicator_engine_requires_warmup() -> None:
    engine = IndicatorEngine()
    first = engine.update("1m", make_bar(0))

    assert first["vwap"] is not None
    assert first["ema50"] is not None
    assert first["ema200"] is not None
    assert first["bb_upper"] is None
    assert first["rsi"] is None
    assert first["adx"] is None
    assert first["atr"] is None

    with pytest.raises(ValueError):
        engine.update(cast(Timeframe, "5m"), make_bar(1))


def test_indicator_engine_produces_indicators_after_warmup() -> None:
    engine = IndicatorEngine()
    bars = [make_bar(i) for i in range(30)]

    latest = None
    for bar in bars:
        latest = engine.update("1m", bar)

    assert latest is not None
    for key in ("bb_upper", "bb_middle", "bb_lower", "rsi", "adx", "atr"):
        assert latest[key] is not None

    # get_latest should match the last update
    assert engine.get_latest("1m") == latest

    # warmup API should behave identically
    engine2 = IndicatorEngine()
    engine2.warmup("1m", bars)
    latest2 = engine2.get_latest("1m")
    for key in ("bb_upper", "bb_middle", "bb_lower", "rsi", "adx", "atr"):
        assert latest2[key] is not None


def test_indicator_engine_precise_on_flat_series() -> None:
    engine = IndicatorEngine()
    latest = None
    for i in range(250):
        bar: Bar = {
            "open": 100.0,
            "high": 100.0,
            "low": 100.0,
            "close": 100.0,
            "volume": 10.0,
            "start_ms": i * 60_000,
            "end_ms": i * 60_000 + 60_000,
            "symbol": "BTCUSDT",
            "timeframe": "1m",
        }
        latest = engine.update("1m", bar)

    assert latest is not None
    assert latest["vwap"] == pytest.approx(100.0)
    assert latest["ema50"] == pytest.approx(100.0)
    assert latest["ema200"] == pytest.approx(100.0)
    assert latest["bb_upper"] == pytest.approx(100.0)
    assert latest["bb_middle"] == pytest.approx(100.0)
    assert latest["bb_lower"] == pytest.approx(100.0)
    assert latest["rsi"] == pytest.approx(50.0)
    assert latest["adx"] == pytest.approx(0.0)
    assert latest["atr"] == pytest.approx(0.0)


def test_indicator_engine_vwap_respects_volume_weights() -> None:
    engine = IndicatorEngine()
    bar1: Bar = {
        "open": 100.0,
        "high": 100.0,
        "low": 100.0,
        "close": 100.0,
        "volume": 10.0,
        "start_ms": 0,
        "end_ms": 60_000,
        "symbol": "BTCUSDT",
        "timeframe": "1m",
    }
    bar2: Bar = {
        "open": 200.0,
        "high": 200.0,
        "low": 200.0,
        "close": 200.0,
        "volume": 10.0,
        "start_ms": 60_000,
        "end_ms": 120_000,
        "symbol": "BTCUSDT",
        "timeframe": "1m",
    }

    engine.update("1m", bar1)
    latest = engine.update("1m", bar2)

    assert latest["vwap"] == pytest.approx(150.0)
