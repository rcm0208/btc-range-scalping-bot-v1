from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterator, Optional

import pytest

from src.backtester import Backtester
from src.core.indicator_engine import IndicatorEngine
from src.core.risk_manager import RiskManager, RiskParams
from src.utils import Bar, Indicators, OpenPosition, Signal, Timeframe


def _make_bar(i: int, *, close: float = 100.0, timeframe: Timeframe = "1m") -> Bar:
    step = 60_000 if timeframe == "1m" else 900_000
    return {
        "open": close,
        "high": close,
        "low": close,
        "close": close,
        "volume": 1.0,
        "start_ms": i * step,
        "end_ms": (i + 1) * step,
        "symbol": "BTC",
        "timeframe": timeframe,
    }


class StubDataProvider:
    def __init__(self, bars_1m: list[Bar], bars_15m: list[Bar]) -> None:
        self.bars_1m = bars_1m
        self.bars_15m = bars_15m

    def load_ohlcv(self, timeframe: str, start: datetime, end: datetime) -> Iterator[Bar]:
        _ = start, end  # unused in stub
        if timeframe == "1m":
            return iter(self.bars_1m)
        if timeframe == "15m":
            return iter(self.bars_15m)
        raise ValueError(f"Unsupported timeframe in stub: {timeframe}")


@dataclass
class StubStrategy:
    """Deterministic signals for backtester fill/fee validation."""

    exit_price: float
    enter_emitted: bool = False

    def update(
        self,
        bar_1m: Bar,
        indicators_1m: Indicators,
        bar_15m: Optional[Bar] = None,
        indicators_15m: Optional[Indicators] = None,
        open_position: Optional[OpenPosition] = None,
    ) -> Signal:
        _ = bar_1m, indicators_1m, bar_15m, indicators_15m
        if not self.enter_emitted:
            self.enter_emitted = True
            return {
                "type": "enter",
                "side": "long",
                "reason": "enter_long",
                "tp_level": self.exit_price,
                "sl_level": self.exit_price - 10,
                "timeout_ms": 10 * 60_000,
                "context": None,
            }
        if open_position is not None:
            return {
                "type": "exit",
                "side": "long",
                "reason": "take_profit",
                "tp_level": open_position["tp_level"],
                "sl_level": open_position["sl_level"],
                "timeout_ms": open_position["timeout_ms"],
                "context": {"price": self.exit_price},
            }
        return {
            "type": "hold",
            "side": None,
            "reason": "no_signal",
            "tp_level": None,
            "sl_level": None,
            "timeout_ms": None,
            "context": None,
        }


def test_backtester_applies_slippage_and_fees_on_trade() -> None:
    bars_1m = [_make_bar(0, close=100.0), _make_bar(1, close=104.0)]
    provider = StubDataProvider(bars_1m, [])
    strategy = StubStrategy(exit_price=105.0)
    risk = RiskManager(
        RiskParams(
            max_open_positions=1,
            cooldown_minutes=0,
            max_consecutive_losses=3,
            use_daily_loss_limit=False,
            daily_loss_limit_pct=-1.0,
        )
    )
    backtester = Backtester(
        data_provider=provider,
        indicator_engine=IndicatorEngine(),
        strategy=strategy,  # type: ignore[arg-type]
        risk_manager=risk,
        fee_rate=0.0005,
        slippage_bps=0.001,
    )

    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    end = start + timedelta(minutes=2)
    result = backtester.run(start, end)

    assert len(result.trades) == 1
    trade = result.trades[0]
    expected_entry = 100.0 * 1.001  # slippage worsens long entry
    expected_exit = 105.0 * 0.999  # slippage worsens long exit (sell)
    gross = (expected_exit - expected_entry) / expected_entry
    size = 1.0 / expected_entry
    entry_fee = 1.0 * 0.0005
    exit_fee = (size * expected_exit) * 0.0005
    fee_pct = entry_fee + exit_fee
    expected_net = gross - fee_pct

    assert trade.entry_price == pytest.approx(expected_entry)
    assert trade.exit_price == pytest.approx(expected_exit)
    assert trade.notional == pytest.approx(1.0)
    assert trade.gross_return_pct == pytest.approx(gross)
    assert trade.net_return_pct == pytest.approx(expected_net)
    assert trade.net_pnl == pytest.approx(expected_net * trade.equity_before)
    assert result.final_pnl_pct == pytest.approx(expected_net)
    assert result.final_equity == pytest.approx(1.0 + expected_net)
    assert risk.state.open_positions == 0
    assert risk.state.last_close_time is not None


def test_backtester_handles_short_trade_with_slippage() -> None:
    bars_1m = [_make_bar(0, close=100.0), _make_bar(1, close=95.0)]
    provider = StubDataProvider(bars_1m, [])

    @dataclass
    class ShortStrategy:
        entered: bool = False

        def update(
            self,
            bar_1m: Bar,
            indicators_1m: Indicators,
            bar_15m: Optional[Bar] = None,
            indicators_15m: Optional[Indicators] = None,
            open_position: Optional[OpenPosition] = None,
        ) -> Signal:
            _ = bar_1m, indicators_1m, bar_15m, indicators_15m
            if not self.entered:
                self.entered = True
                return {
                    "type": "enter",
                    "side": "short",
                    "reason": "enter_short",
                    "tp_level": 95.0,
                    "sl_level": 105.0,
                    "timeout_ms": 10 * 60_000,
                    "context": None,
                }
            if open_position:
                return {
                    "type": "exit",
                    "side": "short",
                    "reason": "take_profit",
                    "tp_level": open_position["tp_level"],
                    "sl_level": open_position["sl_level"],
                    "timeout_ms": open_position["timeout_ms"],
                    "context": {"price": 95.0},
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

    strategy = ShortStrategy()
    risk = RiskManager(
        RiskParams(
            max_open_positions=1,
            cooldown_minutes=0,
            max_consecutive_losses=3,
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
        slippage_bps=0.001,
    )

    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    end = start + timedelta(minutes=2)
    result = backtester.run(start, end)

    assert len(result.trades) == 1
    trade = result.trades[0]
    expected_entry_fill = 100.0 * (1 - 0.001)
    expected_exit_fill = 95.0 * (1 + 0.001)
    expected_size = 1.0 / expected_entry_fill
    expected_price_move = expected_entry_fill - expected_exit_fill
    expected_gross_pnl = expected_price_move * expected_size
    assert trade.side == "short"
    assert trade.entry_price == pytest.approx(expected_entry_fill)
    assert trade.exit_price == pytest.approx(expected_exit_fill)
    assert trade.size == pytest.approx(expected_size)
    assert trade.gross_pnl == pytest.approx(expected_gross_pnl)
    assert trade.net_pnl == pytest.approx(expected_gross_pnl)
    assert trade.net_return_pct == pytest.approx(expected_gross_pnl / trade.equity_before)
    assert result.final_equity == pytest.approx(1.0 + expected_gross_pnl)


def test_backtester_fees_use_exit_notional() -> None:
    bars_1m = [_make_bar(0, close=100.0), _make_bar(1, close=150.0)]
    provider = StubDataProvider(bars_1m, [])
    strategy = StubStrategy(exit_price=150.0)
    risk = RiskManager(
        RiskParams(
            max_open_positions=1,
            cooldown_minutes=0,
            max_consecutive_losses=3,
            use_daily_loss_limit=False,
            daily_loss_limit_pct=-1.0,
        )
    )
    fee_rate = 0.001  # 0.1% each side
    backtester = Backtester(
        data_provider=provider,
        indicator_engine=IndicatorEngine(),
        strategy=strategy,  # type: ignore[arg-type]
        risk_manager=risk,
        fee_rate=fee_rate,
        slippage_bps=0.0,
    )

    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    end = start + timedelta(minutes=2)
    result = backtester.run(start, end)

    trade = result.trades[0]
    entry_notional = 1.0  # base_equity=1, position_size=1
    size = entry_notional / 100.0
    exit_notional = size * 150.0  # 1.5
    entry_fee = entry_notional * fee_rate  # 0.001
    exit_fee = exit_notional * fee_rate  # 0.0015
    total_fee = entry_fee + exit_fee  # 0.0025
    gross_pnl = (150.0 - 100.0) * size  # 0.5
    net_pnl = gross_pnl - total_fee

    assert trade.fee_paid_pct == pytest.approx(total_fee)  # equity_before=1.0
    assert trade.gross_pnl == pytest.approx(gross_pnl)
    assert trade.net_pnl == pytest.approx(net_pnl)
    assert result.final_equity == pytest.approx(1.0 + net_pnl)


def test_backtester_clamps_tp_to_target_on_overshoot() -> None:
    # High goes far beyond TP, fill should clamp at TP (no slippage/fees here)
    bars_1m = [
        _make_bar(0, close=100.0, timeframe="1m"),
        {
            **_make_bar(1, close=100.0, timeframe="1m"),
            "high": 120.0,
        },
    ]
    provider = StubDataProvider(bars_1m, [])

    class TpStrategy:
        entered = False

        def update(
            self,
            bar_1m: Bar,
            indicators_1m: Indicators,
            bar_15m: Optional[Bar] = None,
            indicators_15m: Optional[Indicators] = None,
            open_position: Optional[OpenPosition] = None,
        ) -> Signal:
            _ = bar_1m, indicators_1m, bar_15m, indicators_15m
            if not self.entered:
                self.entered = True
                return {
                    "type": "enter",
                    "side": "long",
                    "reason": "enter_long",
                    "tp_level": 105.0,
                    "sl_level": 95.0,
                    "timeout_ms": 60_000,
                    "context": None,
                }
            return {
                "type": "exit",
                "side": "long",
                "reason": "take_profit",
                "tp_level": 105.0,
                "sl_level": 95.0,
                "timeout_ms": 60_000,
                "context": {"price": 120.0},
            }

    strategy = TpStrategy()
    risk = RiskManager(
        RiskParams(
            max_open_positions=1,
            cooldown_minutes=0,
            max_consecutive_losses=3,
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
    end = start + timedelta(minutes=2)
    result = backtester.run(start, end)

    trade = result.trades[0]
    expected_exit = 105.0  # clamped
    size = 1.0 / 100.0
    expected_gross = (expected_exit - 100.0) * size
    assert trade.exit_price == pytest.approx(expected_exit)
    assert trade.gross_pnl == pytest.approx(expected_gross)
    assert trade.net_pnl == pytest.approx(expected_gross)


def test_backtester_clamps_sl_for_short_overshoot() -> None:
    # High overshoots SL for short; fill should clamp at SL (no slippage/fees)
    bars_1m = [
        _make_bar(0, close=100.0, timeframe="1m"),
        {
            **_make_bar(1, close=100.0, timeframe="1m"),
            "high": 120.0,
        },
    ]
    provider = StubDataProvider(bars_1m, [])

    class SlStrategy:
        entered = False

        def update(
            self,
            bar_1m: Bar,
            indicators_1m: Indicators,
            bar_15m: Optional[Bar] = None,
            indicators_15m: Optional[Indicators] = None,
            open_position: Optional[OpenPosition] = None,
        ) -> Signal:
            _ = bar_1m, indicators_1m, bar_15m, indicators_15m
            if not self.entered:
                self.entered = True
                return {
                    "type": "enter",
                    "side": "short",
                    "reason": "enter_short",
                    "tp_level": 95.0,
                    "sl_level": 110.0,
                    "timeout_ms": 60_000,
                    "context": None,
                }
            return {
                "type": "exit",
                "side": "short",
                "reason": "stop_loss",
                "tp_level": 95.0,
                "sl_level": 110.0,
                "timeout_ms": 60_000,
                "context": {"price": 120.0},
            }

    strategy = SlStrategy()
    risk = RiskManager(
        RiskParams(
            max_open_positions=1,
            cooldown_minutes=0,
            max_consecutive_losses=3,
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
    end = start + timedelta(minutes=2)
    result = backtester.run(start, end)

    trade = result.trades[0]
    expected_exit = 110.0  # clamped stop loss
    size = 1.0 / 100.0
    expected_gross = (100.0 - expected_exit) * size
    assert trade.exit_price == pytest.approx(expected_exit)
    assert trade.gross_pnl == pytest.approx(expected_gross)
    assert trade.net_pnl == pytest.approx(expected_gross)


def test_backtester_scales_returns_by_position_size() -> None:
    bars_1m = [_make_bar(0, close=100.0), _make_bar(1, close=110.0)]
    provider = StubDataProvider(bars_1m, [])
    strategy = StubStrategy(exit_price=110.0)
    risk = RiskManager(
        RiskParams(
            max_open_positions=1,
            cooldown_minutes=0,
            max_consecutive_losses=3,
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
        position_size=0.5,
    )

    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    end = start + timedelta(minutes=2)
    result = backtester.run(start, end)

    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.notional == pytest.approx(0.5)
    assert trade.gross_return_pct == pytest.approx(0.05)
    assert trade.net_return_pct == pytest.approx(0.05)
    assert trade.net_pnl == pytest.approx(0.05)
    assert result.final_pnl_pct == pytest.approx(0.05)
    assert result.final_equity == pytest.approx(1.05)


def test_backtester_forced_exit_end_of_data_updates_equity_curve() -> None:
    bars_1m = [_make_bar(0, close=100.0), _make_bar(1, close=101.0), _make_bar(2, close=102.0)]
    provider = StubDataProvider(bars_1m, [])

    class HoldStrategy:
        entered = False

        def update(
            self,
            bar_1m: Bar,
            indicators_1m: Indicators,
            bar_15m: Optional[Bar] = None,
            indicators_15m: Optional[Indicators] = None,
            open_position: Optional[OpenPosition] = None,
        ) -> Signal:
            _ = bar_1m, indicators_1m, bar_15m, indicators_15m
            if not self.entered:
                self.entered = True
                return {
                    "type": "enter",
                    "side": "long",
                    "reason": "enter_long",
                    "tp_level": 200.0,
                    "sl_level": 50.0,
                    "timeout_ms": 60_000,  # larger than series but unused
                    "context": None,
                }
            if open_position:
                return {
                    "type": "hold",
                    "side": None,
                    "reason": "hold",
                    "tp_level": None,
                    "sl_level": None,
                    "timeout_ms": None,
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

    strategy = HoldStrategy()
    risk = RiskManager(
        RiskParams(
            max_open_positions=1,
            cooldown_minutes=0,
            max_consecutive_losses=3,
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
    end = start + timedelta(minutes=3)
    result = backtester.run(start, end)

    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.reason == "end_of_data"
    assert trade.exit_price == pytest.approx(102.0)
    assert result.equity_curve[-1][1] == pytest.approx(result.final_pnl_pct)
    assert result.final_equity == pytest.approx(1.02)


def test_backtester_respects_cooldown_and_blocks_reentry() -> None:
    bars_1m = [_make_bar(0), _make_bar(1, close=101.0), _make_bar(2, close=102.0)]
    provider = StubDataProvider(bars_1m, [])

    class CooldownReenterStrategy:
        entered = 0
        exited_once = False

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
                self.exited_once = True
                return {
                    "type": "exit",
                    "side": "long",
                    "reason": "take_profit",
                    "tp_level": open_position["tp_level"],
                    "sl_level": open_position["sl_level"],
                    "timeout_ms": open_position["timeout_ms"],
                    "context": {"price": float(bar_1m["close"])},
                }
            if self.entered == 0:
                self.entered += 1
                return {
                    "type": "enter",
                    "side": "long",
                    "reason": "enter_long",
                    "tp_level": 200.0,
                    "sl_level": 50.0,
                    "timeout_ms": 60_000,
                    "context": None,
                }
            if self.exited_once and self.entered == 1:
                self.entered += 1
                return {
                    "type": "enter",
                    "side": "long",
                    "reason": "enter_long_reentry",
                    "tp_level": 200.0,
                    "sl_level": 50.0,
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

    strategy = CooldownReenterStrategy()
    risk = RiskManager(
        RiskParams(
            max_open_positions=1,
            cooldown_minutes=2,
            max_consecutive_losses=3,
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
    end = start + timedelta(minutes=3)
    result = backtester.run(start, end)

    assert len(result.trades) == 1
    assert risk.state.open_positions == 0
    assert strategy.entered == 2  # 2回目のエントリーシグナルは出たがブロックされた
    # 再エントリーシグナルは cooldown 中に拒否されるため trades は増えない
    assert result.trades[0].exit_time_ms == bars_1m[1]["end_ms"]


def test_backtester_blocks_after_losing_streak_limit() -> None:
    bars_1m = [_make_bar(0, close=100.0), _make_bar(1, close=99.0), _make_bar(2, close=98.0)]
    provider = StubDataProvider(bars_1m, [])

    class LosingStrategy:
        enter_count = 0

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
                # exit at lower price to realize loss
                return {
                    "type": "exit",
                    "side": "long",
                    "reason": "stop_loss",
                    "tp_level": open_position["tp_level"],
                    "sl_level": open_position["sl_level"],
                    "timeout_ms": open_position["timeout_ms"],
                    "context": {"price": float(bar_1m["close"])},
                }
            self.enter_count += 1
            return {
                "type": "enter",
                "side": "long",
                "reason": "enter_long",
                "tp_level": float(bar_1m["close"]) * 2,
                "sl_level": float(bar_1m["close"]) * 0.5,
                "timeout_ms": 60_000,
                "context": None,
            }

    strategy = LosingStrategy()
    risk = RiskManager(
        RiskParams(
            max_open_positions=1,
            cooldown_minutes=0,
            max_consecutive_losses=1,
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
    end = start + timedelta(minutes=3)
    result = backtester.run(start, end)

    assert len(result.trades) == 1  # 2回目以降は losing_streak 停止で拒否
    assert risk.state.stopped_reason == "losing_streak"
    assert risk.state.losing_streak == 1
    assert strategy.enter_count >= 1


class RecordingStrategy:
    """Record when 15m bars are supplied to update()."""

    def __init__(self) -> None:
        self.seen_15m_end: Optional[int] = None

    def update(
        self,
        bar_1m: Bar,
        indicators_1m: Indicators,
        bar_15m: Optional[Bar] = None,
        indicators_15m: Optional[Indicators] = None,
        open_position: Optional[OpenPosition] = None,
    ) -> Signal:
        _ = indicators_1m, indicators_15m, open_position
        if bar_15m is not None:
            self.seen_15m_end = bar_15m["end_ms"]
        return {
            "type": "hold",
            "side": None,
            "reason": "noop",
            "tp_level": None,
            "sl_level": None,
            "timeout_ms": None,
            "context": None,
        }


def test_backtester_passes_15m_bar_at_boundary() -> None:
    bars_1m = [_make_bar(i) for i in range(15)]
    bars_15m = [_make_bar(0, timeframe="15m")]
    provider = StubDataProvider(bars_1m, bars_15m)
    strategy = RecordingStrategy()
    risk = RiskManager(
        RiskParams(
            max_open_positions=1,
            cooldown_minutes=0,
            max_consecutive_losses=3,
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
    end = start + timedelta(minutes=15)
    backtester.run(start, end)

    assert strategy.seen_15m_end == bars_15m[0]["end_ms"]
