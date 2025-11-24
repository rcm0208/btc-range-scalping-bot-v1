from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

try:
    import yaml
except ImportError:  # pragma: no cover - optional dependency handled at runtime
    yaml = None  # type: ignore[assignment]

from src.backtester import Backtester
from src.core.indicator_engine import IndicatorEngine
from src.core.risk_manager import RiskManager, RiskParams
from src.core.strategy_core import EntryParams, RegimeParams, StrategyCore
from src.infra.data_provider import DataProvider


def load_yaml(path: Path) -> Dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if yaml is None:
        return json.loads(text)
    return yaml.safe_load(text) or {}


def parse_dt(value: str) -> datetime:
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    elif dt.tzinfo != timezone.utc:
        raise ValueError(f"datetime must be UTC, got {dt.tzinfo}")
    return dt


def run_backtest_from_configs(
    *,
    env_path: Path,
    strategy_path: Path,
    risk_path: Path,
    start: datetime,
    end: datetime,
    output_path: Path,
    position_size: float,
    base_equity: float,
) -> None:
    env_cfg = load_yaml(env_path)
    strat_cfg = load_yaml(strategy_path)
    risk_cfg = load_yaml(risk_path)

    _validate_required(env_cfg, ["data_paths", "taker_fee_pct"])
    _validate_required(env_cfg.get("data_paths", {}), ["ohlcv_1m", "ohlcv_15m"])
    _validate_required(strat_cfg, ["vwap_deviation_pct_long", "vwap_deviation_pct_short", "rsi_long_max", "rsi_short_min", "tp_pct", "sl_pct", "timeout_minutes", "regime"])
    _validate_required(risk_cfg, ["max_open_positions", "cooldown_minutes", "max_consecutive_losses", "use_daily_loss_limit", "daily_loss_limit_pct"])
    _validate_required(strat_cfg.get("regime", {}), ["adx_max", "bb_width_pct_max", "ema_flatness_threshold", "ema_spread_pct_max"])

    data_paths = env_cfg.get("data_paths") or {}
    provider = DataProvider(
        timeframe_paths={
            "1m": str(data_paths.get("ohlcv_1m", "")),
            "15m": str(data_paths.get("ohlcv_15m", "")),
        }
    )

    regime = strat_cfg.get("regime", {})
    regime_params = RegimeParams(
        adx_max=regime["adx_max"],
        bb_width_pct_max=regime["bb_width_pct_max"],
        ema_flatness_threshold=regime["ema_flatness_threshold"],
        ema_spread_pct_max=regime["ema_spread_pct_max"],
        vwap_reversion_check=regime.get("vwap_reversion_check", True),
        vwap_deviation_pct_max=regime.get("vwap_deviation_pct_max"),
    )
    entry_params = EntryParams(
        vwap_deviation_pct_long=strat_cfg["vwap_deviation_pct_long"],
        vwap_deviation_pct_short=strat_cfg["vwap_deviation_pct_short"],
        rsi_long_max=strat_cfg["rsi_long_max"],
        rsi_short_min=strat_cfg["rsi_short_min"],
        tp_pct=strat_cfg["tp_pct"],
        sl_pct=strat_cfg["sl_pct"],
        timeout_minutes=strat_cfg["timeout_minutes"],
        pin_bar_ratio=strat_cfg.get("pin_bar_ratio", 2.0),
    )
    strategy = StrategyCore(regime_params=regime_params, entry_params=entry_params)

    risk_params = RiskParams(
        max_open_positions=risk_cfg["max_open_positions"],
        cooldown_minutes=risk_cfg["cooldown_minutes"],
        max_consecutive_losses=risk_cfg["max_consecutive_losses"],
        use_daily_loss_limit=risk_cfg["use_daily_loss_limit"],
        daily_loss_limit_pct=risk_cfg["daily_loss_limit_pct"],
    )
    risk_manager = RiskManager(risk_params)

    slippage_model = env_cfg.get("slippage_model", {})
    slippage_bps = float(slippage_model.get("value", 0.0))
    fee_rate = float(env_cfg.get("taker_fee_pct", 0.0))

    backtester = Backtester(
        data_provider=provider,
        indicator_engine=IndicatorEngine(),
        strategy=strategy,
        risk_manager=risk_manager,
        fee_rate=fee_rate,
        slippage_bps=slippage_bps,
        position_size=position_size,
        base_equity=base_equity,
    )
    result = backtester.run(start=start, end=end)

    output = {
        "summary": asdict(result.summary),
        "final_pnl_pct": result.final_pnl_pct,
        "final_equity": result.final_equity,
        "base_equity": result.base_equity,
        "trades": [asdict(t) for t in result.trades],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run backtest and output summary JSON.")
    parser.add_argument("--env", dest="env_path", default="config/env.yaml")
    parser.add_argument("--strategy", dest="strategy_path", default="config/strategy.yaml")
    parser.add_argument("--risk", dest="risk_path", default="config/risk.yaml")
    parser.add_argument("--start", required=True, help="ISO8601 start datetime (UTC).")
    parser.add_argument("--end", required=True, help="ISO8601 end datetime (UTC).")
    parser.add_argument("--output", default="backtest_result.json")
    parser.add_argument("--position-size", type=float, default=1.0)
    parser.add_argument("--base-equity", type=float, default=1.0)
    args = parser.parse_args()

    start_dt = parse_dt(args.start)
    end_dt = parse_dt(args.end)
    if start_dt >= end_dt:
        parser.error("--start must be earlier than --end")

    run_backtest_from_configs(
        env_path=Path(args.env_path),
        strategy_path=Path(args.strategy_path),
        risk_path=Path(args.risk_path),
        start=start_dt,
        end=end_dt,
        output_path=Path(args.output),
        position_size=float(args.position_size),
        base_equity=float(args.base_equity),
    )


if __name__ == "__main__":
    main()


def _validate_required(cfg: Dict[str, Any], required_keys: list[str]) -> None:
    missing = [k for k in required_keys if k not in cfg or cfg[k] in (None, "")]
    if missing:
        raise ValueError(f"Missing required config keys: {missing}")
