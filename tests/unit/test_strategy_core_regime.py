from __future__ import annotations

import pytest

from src.core.strategy_core import EntryParams, RegimeEvaluation, RegimeParams, StrategyCore
from src.utils import Bar, Indicators, OpenPosition


def make_bar(close: float = 100.0) -> Bar:
    return {
        "open": close,
        "high": close,
        "low": close,
        "close": close,
        "volume": 1.0,
        "start_ms": 0,
        "end_ms": 60_000,
        "symbol": "BTCUSDT",
        "timeframe": "15m",
    }


def make_indicators(
    *,
    adx: float,
    bb_upper: float,
    bb_lower: float,
    ema50: float,
    ema200: float,
    vwap: float,
) -> Indicators:
    return {
        "vwap": vwap,
        "bb_upper": bb_upper,
        "bb_middle": (bb_upper + bb_lower) / 2,
        "bb_lower": bb_lower,
        "rsi": None,
        "adx": adx,
        "ema50": ema50,
        "ema200": ema200,
        "atr": None,
    }


def default_params() -> RegimeParams:
    return RegimeParams(
        adx_max=20,
        bb_width_pct_max=0.005,
        ema_flatness_threshold=0.0001,
        ema_spread_pct_max=0.0015,
        vwap_reversion_check=True,
    )


def default_entry_params() -> EntryParams:
    return EntryParams(
        vwap_deviation_pct_long=0.006,
        vwap_deviation_pct_short=0.006,
        rsi_long_max=25,
        rsi_short_min=75,
        tp_pct=0.003,
        sl_pct=-0.0022,
        timeout_minutes=12,
    )


def test_regime_turns_on_after_flat_emas() -> None:
    params = default_params()
    core = StrategyCore(params, default_entry_params())
    bar = make_bar()
    indicators = make_indicators(
        adx=15,
        bb_upper=100.1,
        bb_lower=99.9,
        ema50=100.0,
        ema200=100.0,
        vwap=100.0,
    )

    first = core.update_regime(bar, indicators)
    assert not first.is_range
    assert first.reason == "ema_slope_uninitialized"

    second = core.update_regime(bar, indicators)
    assert second.is_range
    assert second.reason == "range_on"
    assert core.regime_on is True


def test_regime_turns_off_when_adx_exceeds_threshold() -> None:
    params = default_params()
    core = StrategyCore(params, default_entry_params())
    bar = make_bar()

    ok_indicators = make_indicators(
        adx=15,
        bb_upper=100.05,
        bb_lower=99.95,
        ema50=100.0,
        ema200=100.0,
        vwap=100.0,
    )
    core.update_regime(bar, ok_indicators)  # seed slope state
    on_state = core.update_regime(bar, ok_indicators)
    assert on_state.is_range

    bad_adx = make_indicators(
        adx=25,
        bb_upper=100.05,
        bb_lower=99.95,
        ema50=100.0,
        ema200=100.0,
        vwap=100.0,
    )
    off_state = core.update_regime(bar, bad_adx)
    assert not off_state.is_range
    assert off_state.reason == "adx_above_threshold"
    assert core.regime_on is False


def test_regime_requires_indicator_availability() -> None:
    params = default_params()
    core = StrategyCore(params, default_entry_params())
    bar = make_bar()
    partial_indicators: Indicators = {
        "vwap": None,
        "bb_upper": None,
        "bb_middle": None,
        "bb_lower": None,
        "rsi": None,
        "adx": None,
        "ema50": None,
        "ema200": None,
        "atr": None,
    }

    result: RegimeEvaluation = core.update_regime(bar, partial_indicators)
    assert not result.is_range
    assert result.reason == "indicators_warming_up"
    assert core.regime_on is False


def test_skip_when_regime_off() -> None:
    core = StrategyCore(default_params(), default_entry_params())
    bar_1m = make_bar(close=100.0)
    indicators_1m: Indicators = {
        "vwap": 100.0,
        "bb_upper": 101.0,
        "bb_middle": 100.0,
        "bb_lower": 99.0,
        "rsi": 50.0,
        "adx": None,
        "ema50": None,
        "ema200": None,
        "atr": None,
    }

    signal = core.update(bar_1m, indicators_1m)
    assert signal["type"] == "skip"
    assert signal["reason"] == "regime_off"


def test_hold_when_no_entry_conditions_met() -> None:
    core = StrategyCore(default_params(), default_entry_params())
    bar_15m = make_bar(close=100.0)
    indicators_15m = make_indicators(
        adx=15,
        bb_upper=100.1,
        bb_lower=99.9,
        ema50=100.0,
        ema200=100.0,
        vwap=100.0,
    )
    core.update_regime(bar_15m, indicators_15m)
    core.update_regime(bar_15m, indicators_15m)

    bar_1m = make_bar(close=100.0)
    indicators_1m: Indicators = {
        "vwap": 100.0,
        "bb_upper": 101.0,
        "bb_middle": 100.0,
        "bb_lower": 99.0,
        "rsi": 50.0,
        "adx": None,
        "ema50": None,
        "ema200": None,
        "atr": None,
    }
    signal = core.update(bar_1m, indicators_1m)
    assert signal["type"] == "hold"
    assert signal["reason"] == "no_entry_conditions_met"


def test_enter_long_when_conditions_met() -> None:
    core = StrategyCore(default_params(), default_entry_params())
    bar_15m = make_bar(close=100.0)
    indicators_15m = make_indicators(
        adx=15,
        bb_upper=100.2,
        bb_lower=99.8,
        ema50=100.0,
        ema200=100.0,
        vwap=100.0,
    )
    core.update_regime(bar_15m, indicators_15m)
    core.update_regime(bar_15m, indicators_15m)

    bar_1m: Bar = {
        **make_bar(close=99.2),
        "open": 98.9,
        "high": 99.4,
        "low": 98.7,
    }
    indicators_1m: Indicators = {
        "vwap": 100.0,
        "bb_upper": 101.0,
        "bb_middle": 100.0,
        "bb_lower": 99.2,
        "rsi": 20.0,
        "adx": None,
        "ema50": None,
        "ema200": None,
        "atr": None,
    }

    signal = core.update(bar_1m, indicators_1m)
    assert signal["type"] == "enter"
    assert signal["side"] == "long"
    assert signal["tp_level"] is not None and signal["tp_level"] > bar_1m["close"]
    assert signal["sl_level"] is not None and signal["sl_level"] < bar_1m["close"]


def test_exit_on_take_profit_hits_high() -> None:
    core = StrategyCore(default_params(), default_entry_params())
    bar_1m: Bar = {
        **make_bar(close=101.0),
        "high": 102.0,
        "low": 100.5,
    }
    indicators_1m: Indicators = {
        "vwap": None,
        "bb_upper": None,
        "bb_middle": None,
        "bb_lower": None,
        "rsi": None,
        "adx": None,
        "ema50": None,
        "ema200": None,
        "atr": None,
    }
    open_position: OpenPosition = {
        "side": "long",
        "entry_price": 100.0,
        "entry_time_ms": 0,
        "tp_level": 101.5,
        "sl_level": 99.0,
        "timeout_ms": 60_000,
    }

    signal = core.update(bar_1m, indicators_1m, open_position=open_position)
    assert signal["type"] == "exit"
    assert signal["reason"] == "take_profit"
    assert signal["side"] == "long"
