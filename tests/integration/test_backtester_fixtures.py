from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pyarrow.parquet as pq
import pytest

from src.backtester import Backtester
from src.core.indicator_engine import IndicatorEngine
from src.core.risk_manager import RiskManager, RiskParams
from src.core.strategy_core import EntryParams, RegimeParams, StrategyCore
from src.infra.data_provider import DataProvider

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures"
ONE_MIN_PATH = FIXTURE_DIR / "ohlcv_1m.parquet"
FIFTEEN_MIN_PATH = FIXTURE_DIR / "ohlcv_15m.parquet"


def _to_datetime(ms: int) -> datetime:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)


def test_fixture_parquets_are_well_formed() -> None:
    table_1m = pq.read_table(ONE_MIN_PATH)
    table_15m = pq.read_table(FIFTEEN_MIN_PATH)

    expected_cols = {
        "open",
        "high",
        "low",
        "close",
        "volume",
        "start_ms",
        "end_ms",
        "symbol",
        "timeframe",
    }
    assert set(table_1m.column_names) == expected_cols
    assert set(table_15m.column_names) == expected_cols

    bars_1m = table_1m.to_pylist()
    bars_15m = table_15m.to_pylist()

    assert len(bars_1m) == 60
    assert len(bars_15m) == 4
    assert all(bar["timeframe"] == "1m" for bar in bars_1m)
    assert all(bar["timeframe"] == "15m" for bar in bars_15m)

    # Timestamps should be contiguous and share the same window boundaries
    assert all(
        bars_1m[i]["start_ms"] < bars_1m[i + 1]["start_ms"]
        for i in range(len(bars_1m) - 1)
    )
    assert bars_1m[0]["start_ms"] == bars_15m[0]["start_ms"]
    assert bars_1m[-1]["end_ms"] == bars_15m[-1]["end_ms"]


def test_backtester_smoke_runs_on_fixture_data() -> None:
    bars_1m = pq.read_table(ONE_MIN_PATH).to_pylist()
    start = _to_datetime(bars_1m[0]["start_ms"])
    end = _to_datetime(bars_1m[-1]["end_ms"])

    provider = DataProvider({"1m": str(ONE_MIN_PATH), "15m": str(FIFTEEN_MIN_PATH)})
    indicator_engine = IndicatorEngine(
        bb_period=3,
        bb_std=1.0,
        rsi_period=3,
        adx_period=1,
        ema_fast_period=5,
        ema_slow_period=8,
        atr_period=3,
    )
    regime_params = RegimeParams(
        adx_max=200.0,
        bb_width_pct_max=0.2,
        ema_flatness_threshold=0.2,
        ema_spread_pct_max=0.2,
        vwap_reversion_check=False,
        vwap_deviation_pct_max=None,
    )
    entry_params = EntryParams(
        vwap_deviation_pct_long=0.006,
        vwap_deviation_pct_short=0.006,
        rsi_long_max=35,
        rsi_short_min=70,
        tp_pct=0.003,
        sl_pct=-0.0022,
        timeout_minutes=12,
    )
    strategy = StrategyCore(regime_params=regime_params, entry_params=entry_params)
    risk_manager = RiskManager(
        RiskParams(
            max_open_positions=1,
            cooldown_minutes=4,
            max_consecutive_losses=3,
            use_daily_loss_limit=False,
            daily_loss_limit_pct=-0.02,
        )
    )

    backtester = Backtester(
        data_provider=provider,
        indicator_engine=indicator_engine,
        strategy=strategy,
        risk_manager=risk_manager,
        fee_rate=0.0,
        slippage_bps=0.0,
        position_size=1.0,
        base_equity=1.0,
    )

    result = backtester.run(start=start, end=end)

    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.side == "long"
    assert trade.reason == "take_profit"
    assert result.final_equity == pytest.approx(1.003, rel=1e-6)
    assert result.summary.trades == 1
    assert result.summary.win_rate == pytest.approx(1.0)
