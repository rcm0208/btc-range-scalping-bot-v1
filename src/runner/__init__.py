from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional

try:
    import yaml  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - optional dependency handled at runtime
    yaml = None  # type: ignore[assignment]

from src.backtester import Backtester
from src.core.indicator_engine import IndicatorEngine
from src.core.risk_manager import RiskManager, RiskParams
from src.core.strategy_core import EntryParams, RegimeParams, StrategyCore
from src.infra.broker_client import BrokerClient
from src.infra.data_provider import DataProvider
from src.infra.logging_metrics import get_json_logger
from src.infra.notifier import Notifier

logger = logging.getLogger(__name__)


@dataclass
class ConfigPaths:
    """Configuration file paths for env/strategy/risk."""

    env: Path = Path("config/env.yaml")
    strategy: Path = Path("config/strategy.yaml")
    risk: Path = Path("config/risk.yaml")


@dataclass
class RunFlags:
    """Runtime flags toggled by the operator."""

    emergency_stop_path: Optional[Path] = None
    dry_run: bool = False  # TODO: Implement dry_run support in live mode


@dataclass
class RunnerDependencies:
    env_config: dict[str, Any]
    strategy_config: dict[str, Any]
    risk_config: dict[str, Any]
    data_provider: DataProvider
    indicator_engine: IndicatorEngine
    strategy: StrategyCore
    risk_manager: RiskManager
    logger: logging.LoggerAdapter
    notifier: Optional[Notifier]
    broker_client: Optional[BrokerClient]


def run(
    mode: str,
    config_paths: ConfigPaths | None = None,
    flags: RunFlags | None = None,
    *,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    position_size: float = 1.0,
    base_equity: float = 1.0,
    environ: Mapping[str, str] | None = None,
) -> Any:
    """Entry point for bt/live modes.

    Args:
        mode: "bt" or "live".
        config_paths: Paths to env/strategy/risk configs.
        flags: Runtime flags (e.g., emergency stop).
        start: Backtest start (required for bt).
        end: Backtest end (required for bt).
        position_size: Position size multiplier for bt.
        base_equity: Starting equity for bt.
        environ: Optional environment mapping for dependency construction (defaults to os.environ).
    """
    cfg_paths = config_paths or ConfigPaths()
    run_flags = flags or RunFlags()
    normalized_mode = mode.lower()
    if normalized_mode not in {"bt", "live"}:
        raise ValueError("mode must be 'bt' or 'live'")

    deps = build_dependencies(cfg_paths, environ=environ)
    log = deps.logger

    if _is_emergency_stop(run_flags):
        log.warning("Emergency stop triggered; aborting run.")
        return {"status": "stopped", "reason": "emergency_stop"}

    if normalized_mode == "bt":
        if start is None or end is None:
            raise ValueError("start and end must be provided for backtest mode")
        _ensure_utc_datetime(start, "start")
        _ensure_utc_datetime(end, "end")
        slippage_model = deps.env_config.get("slippage_model", {}) or {}
        slippage_bps = float(slippage_model.get("value", 0.0))
        fee_rate = float(deps.env_config.get("taker_fee_pct", 0.0))
        backtester = Backtester(
            data_provider=deps.data_provider,
            indicator_engine=deps.indicator_engine,
            strategy=deps.strategy,
            risk_manager=deps.risk_manager,
            fee_rate=fee_rate,
            slippage_bps=slippage_bps,
            position_size=position_size,
            base_equity=base_equity,
        )
        log.info(
            "Starting backtest",
            extra={
                "event": "backtest_start",
                "start": start.isoformat(),
                "end": end.isoformat(),
                "position_size": position_size,
                "base_equity": base_equity,
            },
        )
        result = backtester.run(start=start, end=end)
        log.info(
            "Backtest finished",
            extra={
                "event": "backtest_complete",
                "final_equity": result.final_equity,
                "final_pnl_pct": result.final_pnl_pct,
                "trades": len(result.trades),
            },
        )
        return result

    log.info("Live mode placeholder; dependencies initialized.")
    return {"status": "not_implemented", "mode": "live"}


def build_dependencies(
    config_paths: ConfigPaths,
    *,
    environ: Mapping[str, str] | None = None,
) -> RunnerDependencies:
    """Load configs and construct core dependencies."""
    env_cfg, strat_cfg, risk_cfg = load_configs(config_paths)
    env_label = str(env_cfg.get("environment", "bt"))
    logger_adapter = get_json_logger("runner", env_label)
    indicator_engine = IndicatorEngine()
    strategy = StrategyCore(
        regime_params=_build_regime_params(strat_cfg),
        entry_params=_build_entry_params(strat_cfg),
    )
    risk_manager = RiskManager(_build_risk_params(risk_cfg))
    data_provider = _build_data_provider(env_cfg)

    notifier = _build_notifier(env_cfg)
    broker_client = _build_broker_client(env_cfg, environ=environ, logger=logger_adapter)

    return RunnerDependencies(
        env_config=env_cfg,
        strategy_config=strat_cfg,
        risk_config=risk_cfg,
        data_provider=data_provider,
        indicator_engine=indicator_engine,
        strategy=strategy,
        risk_manager=risk_manager,
        logger=logger_adapter,
        notifier=notifier,
        broker_client=broker_client,
    )


def load_configs(paths: ConfigPaths) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Read env/strategy/risk configs."""
    env_cfg = _load_yaml_or_json(paths.env)
    strat_cfg = _load_yaml_or_json(paths.strategy)
    risk_cfg = _load_yaml_or_json(paths.risk)

    _validate_required(
        env_cfg,
        ["data_paths", "taker_fee_pct"],
    )
    _validate_required(
        env_cfg.get("data_paths", {}),
        ["ohlcv_1m", "ohlcv_15m"],
    )
    _validate_required(
        strat_cfg,
        [
            "vwap_deviation_pct_long",
            "vwap_deviation_pct_short",
            "rsi_long_max",
            "rsi_short_min",
            "tp_pct",
            "sl_pct",
            "timeout_minutes",
            "regime",
        ],
    )
    _validate_required(
        strat_cfg.get("regime", {}),
        ["adx_max", "bb_width_pct_max", "ema_flatness_threshold", "ema_spread_pct_max"],
    )
    _validate_required(
        risk_cfg,
        [
            "max_open_positions",
            "cooldown_minutes",
            "max_consecutive_losses",
            "use_daily_loss_limit",
        ],
    )
    if risk_cfg.get("use_daily_loss_limit"):
        _validate_required(risk_cfg, ["daily_loss_limit_pct"])

    return env_cfg, strat_cfg, risk_cfg


def _build_regime_params(cfg: Mapping[str, Any]) -> RegimeParams:
    regime = cfg.get("regime", {}) or {}
    return RegimeParams(
        adx_max=regime["adx_max"],
        bb_width_pct_max=regime["bb_width_pct_max"],
        ema_flatness_threshold=regime["ema_flatness_threshold"],
        ema_spread_pct_max=regime["ema_spread_pct_max"],
        vwap_reversion_check=regime.get("vwap_reversion_check", True),
        vwap_deviation_pct_max=regime.get("vwap_deviation_pct_max"),
    )


def _build_entry_params(cfg: Mapping[str, Any]) -> EntryParams:
    return EntryParams(
        vwap_deviation_pct_long=cfg["vwap_deviation_pct_long"],
        vwap_deviation_pct_short=cfg["vwap_deviation_pct_short"],
        rsi_long_max=cfg["rsi_long_max"],
        rsi_short_min=cfg["rsi_short_min"],
        tp_pct=cfg["tp_pct"],
        sl_pct=cfg["sl_pct"],
        timeout_minutes=cfg["timeout_minutes"],
        pin_bar_ratio=cfg.get("pin_bar_ratio", 2.0),
    )


def _build_risk_params(cfg: Mapping[str, Any]) -> RiskParams:
    return RiskParams(
        max_open_positions=cfg["max_open_positions"],
        cooldown_minutes=cfg["cooldown_minutes"],
        max_consecutive_losses=cfg["max_consecutive_losses"],
        use_daily_loss_limit=cfg["use_daily_loss_limit"],
        daily_loss_limit_pct=cfg.get("daily_loss_limit_pct", 0.0),
    )


def _build_data_provider(env_cfg: Mapping[str, Any]) -> DataProvider:
    data_paths = env_cfg.get("data_paths") or {}
    return DataProvider(
        timeframe_paths={
            "1m": str(data_paths["ohlcv_1m"]),
            "15m": str(data_paths["ohlcv_15m"]),
        }
    )


def _build_notifier(env_cfg: Mapping[str, Any]) -> Optional[Notifier]:
    webhook_url = str(env_cfg.get("slack_webhook_url") or "").strip()
    if not webhook_url:
        return None
    environment = str(env_cfg.get("environment", "bt"))
    return Notifier(webhook_url=webhook_url, environment=environment)


def _build_broker_client(
    env_cfg: Mapping[str, Any],
    *,
    environ: Mapping[str, str] | None = None,
    logger: logging.Logger | logging.LoggerAdapter | None = None,
) -> Optional[BrokerClient]:
    env_vars = environ if environ is not None else os.environ
    private_key = env_vars.get("HL_AGENT_PRIVATE_KEY")
    env_label = str(env_cfg.get("environment", "bt"))
    if not private_key:
        if env_label.lower() == "live":
            if logger:
                logger.warning(
                    "Broker client not initialized: HL_AGENT_PRIVATE_KEY is missing in live environment"
                )
            else:
                logging.getLogger(__name__).warning(
                    "Broker client not initialized: HL_AGENT_PRIVATE_KEY is missing in live environment"
                )
        return None
    api_base = str(env_cfg.get("api_base", "https://api.hyperliquid.xyz"))
    return BrokerClient(api_base=api_base, private_key=private_key)


def _is_emergency_stop(flags: RunFlags) -> bool:
    path = flags.emergency_stop_path
    if not path:
        return False
    try:
        content = path.read_text(encoding="utf-8").strip().lower()
        return content in {"1", "true", "on", "yes", "stop", "halt"}
    except FileNotFoundError:
        return False
    except (PermissionError, OSError) as exc:
        logger.warning("Failed to read emergency stop file: %s", exc)
        return True


def _load_yaml_or_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        data = json.loads(text)
        if not isinstance(data, dict):
            raise TypeError(
                f"Expected dict in config file, got {type(data).__name__}: {path}"
            )
        return data
    if yaml is None:
        raise ImportError(
            "PyYAML is required to load YAML config files. "
            "Install it (see requirements.txt) or use JSON configs."
        )
    data = yaml.safe_load(text)
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise TypeError(f"Expected dict in config file, got {type(data).__name__}: {path}")
    return data


def _validate_required(cfg: Mapping[str, Any], required_keys: list[str]) -> None:
    missing = [k for k in required_keys if k not in cfg or cfg[k] in (None, "")]
    if missing:
        raise ValueError(f"Missing required config keys: {missing}")


def _ensure_utc_datetime(dt: datetime, name: str) -> None:
    if dt.tzinfo is None:
        raise ValueError(f"{name} must be timezone-aware and UTC")
    if dt.tzinfo != timezone.utc:
        raise ValueError(f"{name} must be in UTC, got tz={dt.tzinfo}")


__all__ = [
    "ConfigPaths",
    "RunFlags",
    "RunnerDependencies",
    "build_dependencies",
    "load_configs",
    "run",
]
