from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from src.core.risk_manager import RiskManager, RiskParams
from src.utils import PnlStats


def make_params(**overrides: object) -> RiskParams:
    defaults = {
        "max_open_positions": 1,
        "cooldown_minutes": 4,
        "max_consecutive_losses": 3,
        "use_daily_loss_limit": False,
        "daily_loss_limit_pct": -0.02,
    }
    defaults.update(overrides)
    return RiskParams(**defaults)  # type: ignore[arg-type]


def make_stats(
    *,
    open_positions: int = 0,
    daily_realized_pct: float = 0.0,
    last_close_time: datetime | None = None,
    losing_streak: int = 0,
) -> PnlStats:
    return {
        "open_positions": open_positions,
        "daily_realized_pct": daily_realized_pct,
        "last_close_time": last_close_time,
        "losing_streak": losing_streak,
    }


def test_can_enter_when_no_limits_hit() -> None:
    manager = RiskManager(make_params())
    now = datetime(2025, 1, 1, 12, 0, 0)
    stats = make_stats()

    result = manager.can_enter(now, stats)

    assert result["allowed"] is True


def test_blocks_when_max_open_positions_reached() -> None:
    manager = RiskManager(make_params(max_open_positions=1))
    now = datetime(2025, 1, 1, 12, 0, 0)
    stats = make_stats(open_positions=1)

    result = manager.can_enter(now, stats)

    assert result["allowed"] is False
    assert result["reason"] == "already_open"


def test_blocks_during_cooldown_after_close() -> None:
    manager = RiskManager(make_params(cooldown_minutes=5))
    close_time = datetime(2025, 1, 1, 0, 0, 0)
    manager.on_close(close_time, pnl_pct=0.0, is_win=True)
    stats = make_stats(
        open_positions=0,
        daily_realized_pct=manager.state.daily_realized_pct,
        last_close_time=manager.state.last_close_time,
        losing_streak=manager.state.losing_streak,
    )

    result = manager.can_enter(close_time + timedelta(minutes=4), stats)

    assert result["allowed"] is False
    assert result["reason"] == "cooldown"


def test_stops_after_consecutive_losses() -> None:
    manager = RiskManager(make_params(max_consecutive_losses=3))
    base_time = datetime(2025, 1, 1, 0, 0, 0)
    for i in range(3):
        manager.on_close(base_time + timedelta(minutes=i), pnl_pct=-0.001, is_win=False)
    stats = make_stats(
        open_positions=0,
        daily_realized_pct=manager.state.daily_realized_pct,
        last_close_time=manager.state.last_close_time,
        losing_streak=manager.state.losing_streak,
    )

    result = manager.can_enter(base_time + timedelta(minutes=10), stats)

    assert result["allowed"] is False
    assert result["reason"] == "losing_streak"
    assert manager.state.stopped_reason == "losing_streak"


def test_daily_loss_limit_blocks_when_enabled() -> None:
    manager = RiskManager(make_params(use_daily_loss_limit=True, daily_loss_limit_pct=-0.02))
    base_time = datetime(2025, 1, 1, 0, 0, 0)
    manager.on_close(base_time, pnl_pct=-0.015, is_win=False)
    manager.on_close(base_time + timedelta(minutes=1), pnl_pct=-0.01, is_win=False)
    stats = make_stats(
        open_positions=0,
        daily_realized_pct=manager.state.daily_realized_pct,
        last_close_time=manager.state.last_close_time,
        losing_streak=manager.state.losing_streak,
    )

    result = manager.can_enter(base_time + timedelta(minutes=10), stats)

    assert result["allowed"] is False
    assert result["reason"] == "daily_loss"
    assert manager.state.stopped_reason == "daily_loss"


def test_daily_loss_compounds_returns() -> None:
    """50% win followed by 50% loss should net -25% (not 0%)."""
    manager = RiskManager(make_params(use_daily_loss_limit=True, daily_loss_limit_pct=-0.2))
    base_time = datetime(2025, 1, 1, 0, 0, 0)
    manager.on_close(base_time, pnl_pct=0.5, is_win=True)
    manager.on_close(base_time + timedelta(minutes=1), pnl_pct=-0.5, is_win=False)

    assert manager.state.daily_realized_pct == pytest.approx(-0.25)
    assert manager.state.stopped_reason == "daily_loss"


def test_reset_daily_clears_stop_flags_and_counters() -> None:
    manager = RiskManager(make_params(use_daily_loss_limit=True, daily_loss_limit_pct=-0.02))
    base_time = datetime(2025, 1, 1, 0, 0, 0)
    manager.on_close(base_time, pnl_pct=-0.03, is_win=False)
    manager.reset_daily(base_time + timedelta(days=1))
    stats = make_stats(
        open_positions=0,
        daily_realized_pct=manager.state.daily_realized_pct,
        last_close_time=manager.state.last_close_time,
        losing_streak=manager.state.losing_streak,
    )

    result = manager.can_enter(base_time + timedelta(days=1, minutes=10), stats)

    assert result["allowed"] is True
    assert manager.state.losing_streak == 0
    assert manager.state.daily_realized_pct == 0.0
    assert manager.state.stopped_reason is None


def test_external_stats_enforce_cooldown() -> None:
    manager = RiskManager(make_params(cooldown_minutes=5))
    now = datetime(2025, 1, 1, 12, 0, 0)
    recent_close = now - timedelta(minutes=2)
    stats = make_stats(last_close_time=recent_close)

    result = manager.can_enter(now, stats)

    assert result["allowed"] is False
    assert result["reason"] == "cooldown"


def test_external_losing_streak_blocks_entry() -> None:
    manager = RiskManager(make_params(max_consecutive_losses=2))
    now = datetime(2025, 1, 1, 12, 0, 0)
    stats = make_stats(losing_streak=2)

    result = manager.can_enter(now, stats)

    assert result["allowed"] is False
    assert result["reason"] == "losing_streak"
    assert manager.state.stopped_reason == "losing_streak"


def test_current_state_returns_copy() -> None:
    manager = RiskManager(make_params())
    state_copy = manager.current_state()
    state_copy.open_positions = 5

    assert manager.state.open_positions == 0


def test_on_enter_increments_and_blocks_additional_entries() -> None:
    manager = RiskManager(make_params(max_open_positions=1))
    now = datetime(2025, 1, 1, 12, 0, 0)

    allowed_first = manager.can_enter(now, make_stats())
    assert allowed_first["allowed"] is True

    manager.on_enter()
    # 外部状態が正とみなされるため、直近の内部状態を渡す
    blocked = manager.can_enter(
        now,
        make_stats(open_positions=manager.state.open_positions),
    )
    assert blocked["allowed"] is False
    assert blocked["reason"] == "already_open"


def test_sync_state_prefers_external_open_positions() -> None:
    manager = RiskManager(make_params(max_open_positions=1))
    now = datetime(2025, 1, 1, 12, 0, 0)
    manager.on_enter()
    assert manager.state.open_positions == 1

    # 外部情報で0件と通知された場合、内部カウントより少なくても外部を優先
    manager._sync_state_from_pnl(
        make_stats(
            open_positions=0,
            losing_streak=0,
            daily_realized_pct=0.0,
            last_close_time=now,
        )
    )
    assert manager.state.open_positions == 0


def test_sync_state_clamps_negative_values() -> None:
    manager = RiskManager(make_params())
    now = datetime(2025, 1, 1, 12, 0, 0)

    manager._sync_state_from_pnl(
        make_stats(
            open_positions=-3,
            losing_streak=-2,
            daily_realized_pct=-0.05,
            last_close_time=now,
        )
    )

    assert manager.state.open_positions == 0
    assert manager.state.losing_streak == 0
    assert manager.state.daily_realized_pct == -0.05
