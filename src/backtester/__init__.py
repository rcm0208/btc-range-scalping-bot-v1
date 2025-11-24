from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterator, Optional, Protocol, Sequence, cast

from src.core.indicator_engine import IndicatorEngine
from src.core.risk_manager import RiskManager
from src.core.strategy_core import StrategyCore
from src.utils import Bar, Indicators, OpenPosition, PnlStats, Side, Signal


class DataProviderProtocol(Protocol):
    """Partial protocol for DataProvider / test doubles."""

    def load_ohlcv(self, timeframe: str, start: datetime, end: datetime) -> Iterator[Bar]:
        ...


@dataclass
class BacktestTrade:
    """A single simulated trade outcome."""

    side: Side
    notional: float
    size: float
    entry_price: float
    exit_price: float
    entry_time_ms: int
    exit_time_ms: int
    reason: str
    gross_return_pct: float
    net_return_pct: float
    fee_paid_pct: float
    slippage_cost_pct: float
    gross_pnl: float
    net_pnl: float
    equity_before: float
    equity_after: float


@dataclass
class BacktestResult:
    trades: list[BacktestTrade]
    equity_curve: list[tuple[int, float]]
    final_pnl_pct: float
    final_equity: float


class Backtester:
    """1m/15m リプレイと簡易約定モデルを備えたバックテスター。"""

    def __init__(
        self,
        *,
        data_provider: DataProviderProtocol,
        indicator_engine: IndicatorEngine,
        strategy: StrategyCore,
        risk_manager: RiskManager,
        fee_rate: float = 0.00045,
        slippage_bps: float = 0.0005,
        position_size: float = 1.0,
        base_equity: float = 1.0,
    ) -> None:
        if position_size <= 0:
            raise ValueError("position_size must be positive")
        if fee_rate < 0:
            raise ValueError("fee_rate must be non-negative")
        if slippage_bps < 0:
            raise ValueError("slippage_bps must be non-negative")
        if base_equity <= 0:
            raise ValueError("base_equity must be positive")

        self.data_provider = data_provider
        self.indicator_engine = indicator_engine
        self.strategy = strategy
        self.risk_manager = risk_manager
        self.fee_rate = fee_rate
        self.slippage_bps = slippage_bps
        self.position_size = position_size
        self.base_equity = base_equity

    def run(self, start: datetime, end: datetime) -> BacktestResult:
        bars_1m = list(self.data_provider.load_ohlcv("1m", start, end))
        bars_15m = list(self.data_provider.load_ohlcv("15m", start, end))
        if not bars_1m:
            raise ValueError("No 1m bars available for backtest window")

        trades: list[BacktestTrade] = []
        equity_curve: list[tuple[int, float]] = []

        open_position: Optional[_ActivePosition] = None
        equity = self.base_equity
        idx_15m = 0
        last_reset_date = None

        for bar in bars_1m:
            bar_dt = _ms_to_datetime(bar["end_ms"])
            bar_date = bar_dt.date()
            if last_reset_date is None:
                last_reset_date = bar_date
            elif bar_date != last_reset_date:
                self.risk_manager.reset_daily(bar_dt)
                last_reset_date = bar_date

            bar_15m, indicators_15m, idx_15m = self._advance_15m(
                bars_15m, idx_15m, bar["end_ms"]
            )

            indicators_1m = self.indicator_engine.update("1m", bar)
            signal = self.strategy.update(
                bar_1m=bar,
                indicators_1m=indicators_1m,
                bar_15m=bar_15m,
                indicators_15m=indicators_15m,
                open_position=open_position.position if open_position else None,
            )

            if signal["type"] == "exit" and open_position is not None:
                trade = self._close_position(bar, signal, open_position)
                trades.append(trade)
                equity = trade.equity_after
                self.risk_manager.on_close(bar_dt, trade.net_return_pct, trade.net_return_pct > 0)
                open_position = None
            elif signal["type"] == "enter" and open_position is None:
                check = self.risk_manager.can_enter(bar_dt, self._current_pnl_stats())
                if check["allowed"]:
                    open_position = self._open_position(bar, signal, equity)
                    self.risk_manager.on_enter()
            realized_pct = (equity - self.base_equity) / self.base_equity
            equity_curve.append((bar["end_ms"], realized_pct))

        if open_position is not None:
            last_bar = bars_1m[-1]
            last_dt = _ms_to_datetime(last_bar["end_ms"])
            forced_exit_signal: Signal = {
                "type": "exit",
                "side": open_position.position["side"],
                "reason": "end_of_data",
                "tp_level": open_position.position["tp_level"],
                "sl_level": open_position.position["sl_level"],
                "timeout_ms": open_position.position["timeout_ms"],
                "context": {"bar_close": last_bar["close"]},
            }
            trade = self._close_position(last_bar, forced_exit_signal, open_position)
            trades.append(trade)
            equity = trade.equity_after
            self.risk_manager.on_close(last_dt, trade.net_return_pct, trade.net_return_pct > 0)
            realized_pct = (equity - self.base_equity) / self.base_equity
            # Note: equity_curve already has a point for last_bar; we append again to reflect forced exit.
            equity_curve.append((last_bar["end_ms"], realized_pct))

        final_pnl_pct = (equity - self.base_equity) / self.base_equity
        return BacktestResult(
            trades=trades,
            equity_curve=equity_curve,
            final_pnl_pct=final_pnl_pct,
            final_equity=equity,
        )

    def _advance_15m(
        self,
        bars_15m: Sequence[Bar],
        idx_15m: int,
        current_end_ms: int,
    ) -> tuple[Optional[Bar], Optional[Indicators], int]:
        delivered_bar: Optional[Bar] = None
        delivered_indicators: Optional[Indicators] = None
        while idx_15m < len(bars_15m) and bars_15m[idx_15m]["end_ms"] <= current_end_ms:
            current_bar = bars_15m[idx_15m]
            indicators = self.indicator_engine.update("15m", current_bar)
            if current_bar["end_ms"] == current_end_ms:
                delivered_bar = current_bar
                delivered_indicators = indicators
            idx_15m += 1
        return delivered_bar, delivered_indicators, idx_15m

    def _open_position(self, bar: Bar, signal: Signal, equity: float) -> "_ActivePosition":
        side = signal["side"]
        if side is None:
            raise ValueError("enter signal must include side")
        if signal["tp_level"] is None or signal["sl_level"] is None or signal["timeout_ms"] is None:
            raise ValueError("enter signal must include tp_level, sl_level, and timeout_ms")
        entry_base = float(bar["close"])
        entry_fill = self._apply_slippage(entry_base, side, is_entry=True)
        notional = equity * self.position_size
        size = notional / entry_fill
        position: OpenPosition = {
            "side": side,
            "entry_price": entry_fill,
            "entry_time_ms": int(bar["end_ms"]),
            "tp_level": float(cast(float, signal["tp_level"])),
            "sl_level": float(cast(float, signal["sl_level"])),
            "timeout_ms": int(cast(int, signal["timeout_ms"])),
        }
        return _ActivePosition(position=position, notional=notional, size=size, equity_before=equity)

    def _close_position(
        self, bar: Bar, signal: Signal, open_position: "_ActivePosition"
    ) -> BacktestTrade:
        side = open_position.position["side"]
        exit_base = self._resolve_exit_price(bar, signal, open_position.position)
        exit_fill = self._apply_slippage(exit_base, side, is_entry=False)
        entry_price = float(open_position.position["entry_price"])

        price_move = exit_fill - entry_price if side == "long" else entry_price - exit_fill
        gross_pnl = price_move * open_position.size
        gross_return_pct = gross_pnl / open_position.equity_before
        entry_fee = open_position.notional * self.fee_rate
        exit_notional = open_position.size * exit_fill
        exit_fee = exit_notional * self.fee_rate
        total_fee = entry_fee + exit_fee
        total_fee_pct = total_fee / open_position.equity_before
        # Slippage approximation: symmetric bps scaled by position_size (not exact realized slippage).
        slippage_cost_pct = self.slippage_bps * 2 * self.position_size
        net_pnl = gross_pnl - total_fee
        net_return_pct = net_pnl / open_position.equity_before
        equity_after = open_position.equity_before + net_pnl

        return BacktestTrade(
            side=side,
            notional=open_position.notional,
            size=open_position.size,
            entry_price=entry_price,
            exit_price=exit_fill,
            entry_time_ms=open_position.position["entry_time_ms"],
            exit_time_ms=int(bar["end_ms"]),
            reason=signal["reason"],
            gross_return_pct=gross_return_pct,
            net_return_pct=net_return_pct,
            fee_paid_pct=total_fee_pct,
            slippage_cost_pct=slippage_cost_pct,
            gross_pnl=gross_pnl,
            net_pnl=net_pnl,
            equity_before=open_position.equity_before,
            equity_after=equity_after,
        )

    def _resolve_exit_price(
        self, bar: Bar, signal: Signal, _open_position: OpenPosition
    ) -> float:
        context = signal.get("context") or {}
        hit_price = None
        if isinstance(context, dict):
            hit_price = context.get("price") or context.get("bar_close")

        price = float(hit_price) if isinstance(hit_price, (float, int)) else float(bar["close"])
        side = _open_position["side"]
        tp_level = _open_position.get("tp_level")
        sl_level = _open_position.get("sl_level")

        reason = signal.get("reason")
        if reason == "take_profit" and tp_level is not None:
            if side == "long":
                price = min(price, float(tp_level))
            else:
                price = max(price, float(tp_level))
        elif reason == "stop_loss" and sl_level is not None:
            if side == "long":
                price = max(price, float(sl_level))
            else:
                price = min(price, float(sl_level))
        elif reason == "timeout":
            price = float(bar["close"])

        return price

    def _current_pnl_stats(self) -> PnlStats:
        state = self.risk_manager.state
        return {
            "open_positions": state.open_positions,
            "daily_realized_pct": state.daily_realized_pct,
            "last_close_time": state.last_close_time,
            "losing_streak": state.losing_streak,
        }

    def _apply_slippage(self, price: float, side: Side, *, is_entry: bool) -> float:
        if side == "long":
            return price * (1 + self.slippage_bps) if is_entry else price * (1 - self.slippage_bps)
        return price * (1 - self.slippage_bps) if is_entry else price * (1 + self.slippage_bps)


def _ms_to_datetime(ms: int) -> datetime:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)


@dataclass
class _ActivePosition:
    position: OpenPosition
    notional: float
    size: float
    equity_before: float


__all__ = [
    "BacktestResult",
    "BacktestTrade",
    "Backtester",
    "DataProviderProtocol",
]
