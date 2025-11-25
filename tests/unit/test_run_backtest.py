from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator

import pytest
import pyarrow as pa
import pyarrow.parquet as pq

from scripts.run_backtest import run_backtest_from_configs
from src.utils import Bar, Timeframe


def _write_parquet(path: Path, bars: list[Bar]) -> None:
    table = pa.Table.from_pydict(
        {
            "open": [b["open"] for b in bars],
            "high": [b["high"] for b in bars],
            "low": [b["low"] for b in bars],
            "close": [b["close"] for b in bars],
            "volume": [b["volume"] for b in bars],
            "start_ms": [b["start_ms"] for b in bars],
            "end_ms": [b["end_ms"] for b in bars],
            "symbol": [b["symbol"] for b in bars],
            "timeframe": [b["timeframe"] for b in bars],
        }
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, path)


def _make_bars(tf: Timeframe, closes: list[float], start_ms: int, step_ms: int) -> list[Bar]:
    bars: list[Bar] = []
    current = start_ms
    for close in closes:
        bars.append(
            {
                "open": close,
                "high": close,
                "low": close,
                "close": close,
                "volume": 1.0,
                "start_ms": current,
                "end_ms": current + step_ms,
                "symbol": "BTC",
                "timeframe": tf,
            }
        )
        current += step_ms
    return bars


def test_run_backtest_from_configs_smoke(tmp_path: Path) -> None:
    bars_1m = _make_bars("1m", [100.0, 101.0], 0, 60_000)
    bars_15m = _make_bars("15m", [100.0], 0, 900_000)
    one_path = tmp_path / "ohlcv_1m.parquet"
    fifteen_path = tmp_path / "ohlcv_15m.parquet"
    _write_parquet(one_path, bars_1m)
    _write_parquet(fifteen_path, bars_15m)

    env = {
        "taker_fee_pct": 0.0,
        "slippage_model": {"type": "bps", "value": 0.0},
        "data_paths": {"ohlcv_1m": str(one_path), "ohlcv_15m": str(fifteen_path)},
    }
    strategy = {
        "candle_intervals": {"signal": "1m", "trend": "15m"},
        "regime": {"adx_min": 10, "ema_gap_pct_min": 0.0, "require_trend": False},
        "entry": {
            "bb_touch_buffer_pct": 0.01,
            "rsi_long_max": 100,
            "rsi_short_min": 0,
            "htf_vwap_pullback_pct": 0.0,
            "ema200_guard_pct": 0.1,
            "atr_sl_mult": 1.0,
            "min_stop_pct": 0.0001,
            "rr_ratio": 1.0,
            "timeout_minutes": 10,
        },
    }
    risk = {
        "max_open_positions": 1,
        "cooldown_minutes": 4,
        "max_consecutive_losses": 3,
        "use_daily_loss_limit": False,
        "daily_loss_limit_pct": -0.02,
    }

    env_path = tmp_path / "env.yaml"
    strategy_path = tmp_path / "strategy.yaml"
    risk_path = tmp_path / "risk.yaml"
    env_path.write_text(json.dumps(env), encoding="utf-8")
    strategy_path.write_text(json.dumps(strategy), encoding="utf-8")
    risk_path.write_text(json.dumps(risk), encoding="utf-8")

    output_path = tmp_path / "result.json"
    start = datetime.fromtimestamp(0, tz=timezone.utc)
    end = start + timedelta(minutes=2)

    run_backtest_from_configs(
        env_path=env_path,
        strategy_path=strategy_path,
        risk_path=risk_path,
        start=start,
        end=end,
        output_path=output_path,
        position_size=1.0,
        base_equity=1.0,
    )

    assert output_path.exists()
    data = json.loads(output_path.read_text(encoding="utf-8"))
    assert "summary" in data
    assert "trades" in data
    assert data["summary"]["final_equity"] == pytest.approx(1.0)
