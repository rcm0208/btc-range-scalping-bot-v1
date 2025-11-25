from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from itertools import product
from pathlib import Path
from typing import Any, Dict, Iterable

import yaml

from src.backtester import Backtester
from src.core.indicator_engine import IndicatorEngine
from src.core.risk_manager import RiskManager, RiskParams
from src.core.strategy_core import EntryParams, RegimeParams, StrategyCore
from src.infra.data_provider import DataProvider


def parse_dt(value: str) -> datetime:
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def load_yaml(path: Path) -> Dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def sweep(
    *,
    env_cfg: Dict[str, Any],
    strat_cfg: Dict[str, Any],
    risk_cfg: Dict[str, Any],
    start: datetime,
    end: datetime,
    grid: Dict[str, Iterable[Any]],
    output_dir: Path,
) -> None:
    provider = DataProvider(
        timeframe_paths={
            "15m": env_cfg["data_paths"]["ohlcv_15m"],
        }
    )
    risk_params = RiskParams(
        max_open_positions=risk_cfg["max_open_positions"],
        cooldown_minutes=risk_cfg["cooldown_minutes"],
        max_consecutive_losses=risk_cfg["max_consecutive_losses"],
        use_daily_loss_limit=risk_cfg["use_daily_loss_limit"],
        daily_loss_limit_pct=risk_cfg["daily_loss_limit_pct"],
    )

    results = []
    output_dir.mkdir(parents=True, exist_ok=True)

    combos = list(product(*grid.values()))
    for combo in combos:
        params = dict(zip(grid.keys(), combo))
        entry_params = EntryParams(
            stoch_k_long=params["stoch_k_long"],
            stoch_k_short=params["stoch_k_short"],
            wick_ratio_max=params["wick_ratio_max"],
            atr_multiple=params["atr_multiple"],
            rr_ratio=params["rr_ratio"],
            timeout_minutes=params["timeout_minutes"],
            session_start_hour_utc=params.get("session_start_hour_utc"),
            session_end_hour_utc=params.get("session_end_hour_utc"),
        )

        backtester = Backtester(
            data_provider=provider,
            indicator_engine=IndicatorEngine(),
            strategy=StrategyCore(regime_params=RegimeParams(enabled=True), entry_params=entry_params),
            risk_manager=RiskManager(risk_params),
            fee_rate=env_cfg["taker_fee_pct"],
            slippage_bps=env_cfg.get("slippage_model", {}).get("value", 0.0),
            position_size=1.0,
            base_equity=1.0,
            signal_timeframe="15m",
            trend_timeframe=None,
        )

        result = backtester.run(start=start, end=end)
        summary = asdict(result.summary)
        summary["win_rate"] = summary.get("win_rate", 0) or 0
        results.append(
            {
                "params": params,
                "summary": summary,
                "trades": len(result.trades),
                "final_pnl_pct": result.final_pnl_pct,
            }
        )

    results.sort(key=lambda r: (-(r["summary"]["profit_factor"] or 0), -r["trades"]))
    best = results[0] if results else None
    (output_dir / "grid_results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    if best:
        (output_dir / "best_summary.json").write_text(json.dumps(best, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    env_cfg = load_yaml(Path("config/env.yaml"))
    strat_cfg = load_yaml(Path("config/strategy.yaml"))
    risk_cfg = load_yaml(Path("config/risk.yaml"))

    # フォワード期間を優先（直近データ）
    start = parse_dt("2025-09-01T00:00:00Z")
    end = parse_dt("2025-11-24T00:00:00Z")

    grid = {
        "stoch_k_long": [25, 30],
        "stoch_k_short": [65, 70],
        "wick_ratio_max": [0.3, 0.5],
        "atr_multiple": [1.0, 1.2],
        "rr_ratio": [1.5, 1.7],
        "timeout_minutes": [240, 360],
        "session_start_hour_utc": [None, 12],
        "session_end_hour_utc": [None, 20],
    }

    sweep(
        env_cfg=env_cfg,
        strat_cfg=strat_cfg,
        risk_cfg=risk_cfg,
        start=start,
        end=end,
        grid=grid,
        output_dir=Path("backtests/grid_search_forward"),
    )


if __name__ == "__main__":
    main()
