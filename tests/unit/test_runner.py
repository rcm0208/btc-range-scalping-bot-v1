from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

import pyarrow as pa
import pyarrow.parquet as pq

from src.runner import ConfigPaths, RunFlags, build_dependencies, run
from src.utils import Bar, Timeframe


def _write_parquet(path: Path, bars: Iterable[Bar]) -> None:
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


def _write_configs(base_dir: Path, paths: dict[str, Path]) -> ConfigPaths:
    env_cfg = {
        "api_base": "https://api.hyperliquid.xyz",
        "taker_fee_pct": 0.0,
        "slippage_model": {"type": "bps", "value": 0.0},
        "environment": "bt",
        "slack_webhook_url": "",
        "data_paths": {"ohlcv_1m": str(paths["1m"]), "ohlcv_15m": str(paths["15m"])},
    }
    strategy_cfg = {
        "vwap_deviation_pct_long": 0.006,
        "vwap_deviation_pct_short": 0.006,
        "rsi_long_max": 25,
        "rsi_short_min": 75,
        "tp_pct": 0.003,
        "sl_pct": -0.0022,
        "timeout_minutes": 12,
        "pin_bar_ratio": 2.0,
        "regime": {
            "adx_max": 20,
            "bb_width_pct_max": 0.005,
            "ema_flatness_threshold": 0.0001,
            "ema_spread_pct_max": 0.0015,
            "vwap_reversion_check": True,
            "vwap_deviation_pct_max": 0.005,
        },
    }
    risk_cfg = {
        "max_open_positions": 1,
        "cooldown_minutes": 4,
        "max_consecutive_losses": 3,
        "use_daily_loss_limit": False,
        "daily_loss_limit_pct": -0.02,
    }

    env_path = base_dir / "env.json"
    strat_path = base_dir / "strategy.json"
    risk_path = base_dir / "risk.json"
    env_path.write_text(json.dumps(env_cfg), encoding="utf-8")
    strat_path.write_text(json.dumps(strategy_cfg), encoding="utf-8")
    risk_path.write_text(json.dumps(risk_cfg), encoding="utf-8")
    return ConfigPaths(env=env_path, strategy=strat_path, risk=risk_path)


def test_build_dependencies_with_defaults(tmp_path: Path) -> None:
    cfg_paths = _write_configs(
        tmp_path,
        paths={"1m": tmp_path / "ohlcv_1m.parquet", "15m": tmp_path / "ohlcv_15m.parquet"},
    )
    deps = build_dependencies(cfg_paths)

    assert deps.env_config["data_paths"]["ohlcv_1m"].endswith("ohlcv_1m.parquet")
    assert deps.data_provider is not None
    assert deps.indicator_engine is not None
    assert deps.strategy is not None
    assert deps.risk_manager is not None
    assert deps.logger.extra.get("env") == "bt"  # type: ignore[attr-defined]


def test_run_backtest_mode_returns_result(tmp_path: Path) -> None:
    bars_1m = _make_bars("1m", [100.0, 101.0], 0, 60_000)
    bars_15m = _make_bars("15m", [100.0], 0, 900_000)
    one_path = tmp_path / "ohlcv_1m.parquet"
    fifteen_path = tmp_path / "ohlcv_15m.parquet"
    _write_parquet(one_path, bars_1m)
    _write_parquet(fifteen_path, bars_15m)

    cfg_paths = _write_configs(tmp_path, paths={"1m": one_path, "15m": fifteen_path})
    start = datetime.fromtimestamp(0, tz=timezone.utc)
    end = start + timedelta(minutes=2)

    result = run(
        "bt",
        config_paths=cfg_paths,
        start=start,
        end=end,
        position_size=1.0,
        base_equity=1.0,
    )

    assert hasattr(result, "final_equity")
    assert result.final_equity == 1.0
    assert result.trades == []


def test_run_respects_emergency_stop_flag(tmp_path: Path) -> None:
    cfg_paths = _write_configs(
        tmp_path,
        paths={"1m": tmp_path / "ohlcv_1m.parquet", "15m": tmp_path / "ohlcv_15m.parquet"},
    )
    stop_file = tmp_path / "stop.flag"
    stop_file.write_text("stop", encoding="utf-8")

    result = run(
        "live",
        config_paths=cfg_paths,
        flags=RunFlags(emergency_stop_path=stop_file),
    )

    assert result["status"] == "stopped"
