from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from src.utils import CheckResult, PnlStats


@dataclass
class RiskParams:
    """リスク制限に関するパラメータセット。"""

    max_open_positions: int
    cooldown_minutes: int
    max_consecutive_losses: int
    use_daily_loss_limit: bool
    daily_loss_limit_pct: float


@dataclass
class RiskState:
    """現在のリスク状態を保持する。"""

    open_positions: int = 0
    losing_streak: int = 0
    daily_realized_pct: float = 0.0
    last_close_time: Optional[datetime] = None
    stopped_reason: Optional[str] = None  # losing_streak/daily_loss を想定


class RiskManager:
    """同時ポジション・クールダウン・連敗/日次損失ストップを判定する。"""

    def __init__(self, params: RiskParams) -> None:
        self.params = params
        self.state = RiskState()

    def can_enter(self, now: datetime, pnl_stats: PnlStats) -> CheckResult:
        """エントリー可否を判定する。拒否時は理由を返す。"""
        self._sync_state_from_pnl(pnl_stats)

        if self.state.stopped_reason:
            return {"allowed": False, "reason": self.state.stopped_reason}

        if self.state.open_positions >= self.params.max_open_positions:
            return {"allowed": False, "reason": "already_open"}

        if self._in_cooldown(now):
            return {"allowed": False, "reason": "cooldown"}

        if self.state.losing_streak >= self.params.max_consecutive_losses:
            self.state.stopped_reason = "losing_streak"
            return {"allowed": False, "reason": "losing_streak"}

        if (
            self.params.use_daily_loss_limit
            and self.state.daily_realized_pct <= self.params.daily_loss_limit_pct
        ):
            self.state.stopped_reason = "daily_loss"
            return {"allowed": False, "reason": "daily_loss"}

        return {"allowed": True, "reason": None}

    def on_close(self, now: datetime, pnl_pct: float, is_win: bool) -> None:
        """クローズイベントでステートを更新する。pnl_pct は実現損益率を想定。"""
        self.state.last_close_time = now
        self.state.open_positions = max(0, self.state.open_positions - 1)
        self.state.daily_realized_pct += pnl_pct

        if is_win:
            self.state.losing_streak = 0
        else:
            self.state.losing_streak += 1
            if self.state.losing_streak >= self.params.max_consecutive_losses:
                self.state.stopped_reason = self.state.stopped_reason or "losing_streak"

        if (
            self.params.use_daily_loss_limit
            and self.state.daily_realized_pct <= self.params.daily_loss_limit_pct
        ):
            self.state.stopped_reason = self.state.stopped_reason or "daily_loss"

    def on_enter(self) -> None:
        """エントリー確定時に同時ポジションカウントを増やす。"""
        self.state.open_positions += 1

    def reset_daily(self, now: datetime) -> None:
        """日次境界で状態をリセットする。now は I/F 整合性のために受け取り、将来の境界判定用に予約。"""
        _ = now  # lint 回避・将来利用のため保持
        self.state.losing_streak = 0
        self.state.daily_realized_pct = 0.0
        self.state.stopped_reason = None
        # last_close_time はクールダウン計算に利用するため保持(リセットしない)

    def current_state(self) -> RiskState:
        """現在のステートをコピーで返す。"""
        return RiskState(
            open_positions=self.state.open_positions,
            losing_streak=self.state.losing_streak,
            daily_realized_pct=self.state.daily_realized_pct,
            last_close_time=self.state.last_close_time,
            stopped_reason=self.state.stopped_reason,
        )

    def _sync_state_from_pnl(self, pnl_stats: PnlStats) -> None:
        """外部から渡された損益情報でステートを更新する。"""
        # open_positions は内部カウントを下回らないようにマージする
        self.state.open_positions = max(self.state.open_positions, pnl_stats["open_positions"])
        # losing_streak/daily_realized_pct は外部情報を優先（最新集計を想定）
        self.state.losing_streak = pnl_stats["losing_streak"]
        self.state.daily_realized_pct = pnl_stats["daily_realized_pct"]

        external_last_close = pnl_stats["last_close_time"]
        if external_last_close is not None:
            if (
                self.state.last_close_time is None
                or external_last_close > self.state.last_close_time
            ):
                self.state.last_close_time = external_last_close

    def _in_cooldown(self, now: datetime) -> bool:
        """クールダウン中かを判定する。"""
        if self.state.last_close_time is None:
            return False
        cooldown_end = self.state.last_close_time + timedelta(minutes=self.params.cooldown_minutes)
        return now < cooldown_end


__all__ = ["RiskManager", "RiskParams", "RiskState"]
