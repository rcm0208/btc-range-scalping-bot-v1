from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Iterator, Optional, cast

import pytest

from src.backtester import Backtester
from src.core.indicator_engine import IndicatorEngine
from src.core.risk_manager import RiskManager, RiskParams
from src.utils import Bar, Indicators, OpenPosition, Signal, Timeframe


def _make_bar(i: int, *, close: float) -> Bar:
    return {
        "open": close,
        "high": close,
        "low": close,
        "close": close,
        "volume": 1.0,
        "start_ms": i * 60_000,
        "end_ms": (i + 1) * 60_000,
        "symbol": "BTC",
        "timeframe": "1m",
    }


class StubDataProvider:
    def __init__(self, bars_1m: list[Bar]) -> None:
        self.bars_1m = bars_1m

    def load_ohlcv(self, timeframe: str, start: datetime, end: datetime) -> Iterator[Bar]:
        _ = start, end
        tf: Timeframe = cast(Timeframe, timeframe)
        if tf == "1m":
            return iter(self.bars_1m)
        if tf == "15m":
            return iter([])
        raise ValueError("unsupported timeframe")


class TwoTradeStrategy:
    """Enter, exit, then re-enter, exit on the next bar."""

    def __init__(self) -> None:
        self.state = 0

    def update(
        self,
        bar_1m: Bar,
        indicators_1m: Indicators,
        bar_15m: Optional[Bar] = None,
        indicators_15m: Optional[Indicators] = None,
        open_position: Optional[OpenPosition] = None,
    ) -> Signal:
        _ = indicators_1m, bar_15m, indicators_15m
        if open_position:
            return {
                "type": "exit",
                "side": "long",
                "reason": "take_profit",
                "tp_level": open_position["tp_level"],
                "sl_level": open_position["sl_level"],
                "timeout_ms": open_position["timeout_ms"],
                "context": {"price": float(bar_1m["close"])},
            }
        if self.state < 2:
            self.state += 1
            return {
                "type": "enter",
                "side": "long",
                "reason": f"enter_{self.state}",
                "tp_level": 1_000_000.0,
                "sl_level": 0.0,
                "timeout_ms": 60_000,
                "context": None,
            }
        return {
            "type": "hold",
            "side": None,
            "reason": "noop",
            "tp_level": None,
            "sl_level": None,
            "timeout_ms": None,
            "context": None,
        }


def test_backtest_summary_aggregates_metrics() -> None:
    # Trade1: 100 -> 110 (win), Trade2: 100 -> 90 (loss on higher equity)
    bars = [
        _make_bar(0, close=100.0),
        _make_bar(1, close=110.0),
        _make_bar(2, close=100.0),
        _make_bar(3, close=90.0),
    ]
    provider = StubDataProvider(bars)
    strategy = TwoTradeStrategy()
    risk = RiskManager(
        RiskParams(
            max_open_positions=1,
            cooldown_minutes=0,
            max_consecutive_losses=10,
            use_daily_loss_limit=False,
            daily_loss_limit_pct=-1.0,
        )
    )
    backtester = Backtester(
        data_provider=provider,
        indicator_engine=IndicatorEngine(),
        strategy=strategy,  # type: ignore[arg-type]
        risk_manager=risk,
        fee_rate=0.0,
        slippage_bps=0.0,
    )

    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    end = start + timedelta(minutes=4)
    result = backtester.run(start, end)
    summary = result.summary

    assert summary.trades == 2
    assert summary.wins == 1
    assert summary.losses == 1
    assert summary.win_rate == pytest.approx(0.5)
    assert summary.avg_trade_duration_s == pytest.approx(60.0)
    # equity path: 1.0 -> 1.1 -> 0.99 => total return -1%
    assert summary.total_return_pct == pytest.approx(-0.01)
    assert summary.final_equity == pytest.approx(0.99)
    assert summary.max_drawdown_pct == pytest.approx((1.1 - 0.99) / 1.1)
    # profit factor: 0.1 / 0.11
    assert summary.profit_factor == pytest.approx(0.1 / 0.11)
    assert summary.total_fee_pct_of_base == pytest.approx(0.0)
