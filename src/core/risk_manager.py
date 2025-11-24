from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from src.utils import CheckResult, PnlStats


@dataclass
class RiskParams:
    """リスク制限に関するパラメータセット。

    Attributes:
        max_open_positions: 同時保有可能なポジション数の上限（通常は1）
        cooldown_minutes: ポジションクローズ後の新規エントリー禁止期間（分）
        max_consecutive_losses: 連続損切り回数の上限（この回数に達すると停止）
        use_daily_loss_limit: 日次損失制限を有効化するかどうか
        daily_loss_limit_pct: 日次損失制限の閾値（%、負の値。例: -0.02 = -2%）
    """

    max_open_positions: int
    cooldown_minutes: int
    max_consecutive_losses: int
    use_daily_loss_limit: bool
    daily_loss_limit_pct: float


@dataclass
class RiskState:
    """現在のリスク状態を保持する。

    Attributes:
        open_positions: 現在保有中のポジション数
        losing_streak: 連続損切り回数（勝ちトレードでリセット）
        daily_realized_pct: 当日の累積実現損益率（%）
        last_close_time: 最後にポジションをクローズした時刻（UTC）
        stopped_reason: 停止理由（"losing_streak" | "daily_loss" | None）
    """

    open_positions: int = 0
    losing_streak: int = 0
    daily_realized_pct: float = 0.0
    last_close_time: Optional[datetime] = None
    stopped_reason: Optional[str] = None  # losing_streak/daily_loss を想定


class RiskManager:
    """同時ポジション・クールダウン・連敗/日次損失ストップを判定する。

    リスク管理の中核となるクラス。エントリー可否の判定、ポジション状態の追跡、
    各種制限ルールの適用を行う。

    主な機能:
        - 同時ポジション数の制限
        - クローズ後のクールダウン期間の管理
        - 連続損切り回数による自動停止
        - 日次損失制限による自動停止
        - 外部損益情報との状態同期

    Attributes:
        params: リスク制限パラメータ
        state: 現在のリスク状態
    """

    def __init__(self, params: RiskParams) -> None:
        """RiskManagerを初期化する。

        Args:
            params: リスク制限パラメータ
        """
        self.params = params
        self.state = RiskState()

    def can_enter(self, now: datetime, pnl_stats: PnlStats) -> CheckResult:
        """エントリー可否を判定する。

        外部から渡された損益情報で内部状態を同期した後、各種制限ルールを
        順次評価してエントリーの可否を判定する。

        判定順序:
            1. 停止フラグ（stopped_reason）のチェック
            2. 同時ポジション数の上限チェック
            3. クールダウン期間のチェック
            4. 連続損切り回数のチェック
            5. 日次損失制限のチェック

        Args:
            now: 現在時刻（UTC）
            pnl_stats: 外部から渡される損益・状態情報

        Returns:
            CheckResult: エントリー可否の判定結果
                - allowed=True, reason=None: エントリー可能
                - allowed=False, reason="already_open": 既にポジション保有中
                - allowed=False, reason="cooldown": クールダウン期間中
                - allowed=False, reason="losing_streak": 連続損切り回数の上限到達
                - allowed=False, reason="daily_loss": 日次損失制限到達

        Note:
            このメソッドは内部状態を変更する可能性がある（stopped_reasonの設定）。
        """
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
        """ポジションクローズ時に状態を更新する。

        ポジションがクローズされた際に呼び出され、以下の状態を更新する:
            - 最終クローズ時刻（クールダウン計算用）
            - 保有ポジション数（デクリメント）
            - 日次累積損益率
            - 連続損切り回数（勝ちでリセット、負けでインクリメント）
            - 停止フラグ（連続損切りまたは日次損失の閾値到達時）

        Args:
            now: クローズ時刻（UTC）
            pnl_pct: 実現損益率（%。例: 0.003 = +0.3%, -0.002 = -0.2%）
            is_win: 勝ちトレードかどうか（True: 勝ち、False: 負け）

        Note:
            open_positionsが0の場合でもmax(0, ...)で保護されているため、
            負の値にはならない。
        """
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
        """エントリー確定時に保有ポジション数をインクリメントする。

        can_enterでエントリーが許可された後、実際にポジションを建てた際に
        呼び出される。同時ポジション数の追跡に使用される。

        Note:
            このメソッドはcan_enterの判定後に呼び出されることを想定しているため、
            追加の検証は行わない。
        """
        self.state.open_positions += 1

    def reset_daily(self, now: datetime) -> None:
        """日次境界で状態をリセットする。

        日付が変わった際に呼び出され、以下の状態をリセットする:
            - 連続損切り回数
            - 日次累積損益率
            - 停止フラグ

        Args:
            now: リセット時刻（UTC）。現在は使用していないが、将来的に
                 日次境界の自動判定に使用する可能性があるため保持。

        Note:
            last_close_timeはクールダウン計算に使用するためリセットしない。
        """
        _ = now  # lint 回避・将来利用のため保持
        self.state.losing_streak = 0
        self.state.daily_realized_pct = 0.0
        self.state.stopped_reason = None
        # last_close_time はクールダウン計算に利用するため保持(リセットしない)

    def current_state(self) -> RiskState:
        """現在の状態のコピーを返す。

        内部状態を外部に公開する際に使用する。コピーを返すため、
        返された状態を変更しても内部状態には影響しない。

        Returns:
            RiskState: 現在の状態のコピー
        """
        return RiskState(
            open_positions=self.state.open_positions,
            losing_streak=self.state.losing_streak,
            daily_realized_pct=self.state.daily_realized_pct,
            last_close_time=self.state.last_close_time,
            stopped_reason=self.state.stopped_reason,
        )

    def _sync_state_from_pnl(self, pnl_stats: PnlStats) -> None:
        """外部から渡された損益情報で内部状態を同期する。

        外部システム（backtesterやrunner）から渡される損益情報を使って
        内部状態を更新する。これにより、複数のコンポーネント間で状態の
        整合性を保つことができる。

        同期ルール:
            - open_positions: 外部の正準情報を優先（不整合は将来ログ化を検討）
            - losing_streak: 外部情報を優先（最新集計を想定）
            - daily_realized_pct: 外部情報を優先
            - last_close_time: より新しい時刻を採用

        Args:
            pnl_stats: 外部から渡される損益・状態情報
        """
        external_open_raw = pnl_stats["open_positions"]
        external_open = external_open_raw if external_open_raw >= 0 else 0
        if self.state.open_positions != external_open and self.state.open_positions > 0:
            # TODO: 不整合をログに記録する（現状は外部値を正とする）
            pass
        self.state.open_positions = external_open
        # losing_streak/daily_realized_pct は外部情報を優先(最新集計を想定)
        external_losing = pnl_stats["losing_streak"]
        self.state.losing_streak = external_losing if external_losing >= 0 else 0
        self.state.daily_realized_pct = pnl_stats["daily_realized_pct"]

        external_last_close = pnl_stats["last_close_time"]
        if external_last_close is not None:
            if (
                self.state.last_close_time is None
                or external_last_close > self.state.last_close_time
            ):
                self.state.last_close_time = external_last_close

    def _in_cooldown(self, now: datetime) -> bool:
        """現在がクールダウン期間中かを判定する。

        最後のポジションクローズ時刻から指定された分数が経過していない場合、
        クールダウン期間中と判定する。

        Args:
            now: 現在時刻（UTC）

        Returns:
            bool: クールダウン期間中の場合True、それ以外はFalse
        """
        if self.state.last_close_time is None:
            return False
        cooldown_end = self.state.last_close_time + timedelta(minutes=self.params.cooldown_minutes)
        return now < cooldown_end


__all__ = ["RiskManager", "RiskParams", "RiskState"]
