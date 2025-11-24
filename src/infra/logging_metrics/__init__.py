from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Mapping, Optional

_STD_KEYS = ("timestamp", "level", "module", "event", "env", "message")


class JsonFormatter(logging.Formatter):
    """JSON Lines formatter with fixed standard keys."""

    def format(self, record: logging.LogRecord) -> str:  # type: ignore[override]
        payload: Dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "module": record.name,
            "event": getattr(record, "event", None) or record.getMessage(),
            "env": getattr(record, "env", None),
            "message": record.getMessage(),
        }
        skip_keys = {
            "args",
            "msg",
            "name",
            "levelname",
            "levelno",
            "exc_info",
            "exc_text",
            "stack_info",
            "stacklevel",
            "funcName",
            "lineno",
            "pathname",
            "filename",
            "module",
            "processName",
            "process",
            "thread",
            "threadName",
        }
        for key, value in record.__dict__.items():
            if key.startswith("_"):
                continue
            if key in _STD_KEYS or key in skip_keys:
                continue
            try:
                json.dumps(value)
                payload[key] = value
            except TypeError:
                payload[key] = str(value)
        return json.dumps(payload, ensure_ascii=True)


class _EnvLoggerAdapter(logging.LoggerAdapter):  # type: ignore[misc]
    """Adapter that injects env and ensures event is populated."""

    def process(self, msg: str, kwargs: Mapping[str, Any]) -> tuple[str, Dict[str, Any]]:
        merged: Dict[str, Any] = {}
        if self.extra:
            merged.update(self.extra)
        extra = kwargs.get("extra")
        if extra:
            merged.update(extra)  # type: ignore[arg-type]
        merged.setdefault("event", msg)
        new_kwargs: Dict[str, Any] = dict(kwargs)
        new_kwargs["extra"] = merged
        return msg, new_kwargs


def get_json_logger(name: str, env: str, level: int = logging.INFO) -> logging.LoggerAdapter:
    """Create or get a logger configured with JSON formatter and env label."""
    logger = logging.getLogger(name)
    logger.setLevel(level)
    if not any(isinstance(h, logging.StreamHandler) for h in logger.handlers):
        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)
    logger.propagate = False
    adapter: logging.LoggerAdapter = _EnvLoggerAdapter(logger, {"env": env})  # type: ignore[assignment]
    return adapter


@dataclass
class MetricsRecorder:
    """Lightweight metrics accumulator."""

    trades: int = 0
    wins: int = 0
    losses: int = 0
    cancels: int = 0
    api_errors: int = 0
    custom: Dict[str, float] = field(default_factory=dict)

    def record_trade(self, is_win: Optional[bool] = None) -> None:
        self.trades += 1
        if is_win is True:
            self.wins += 1
        elif is_win is False:
            self.losses += 1

    def record_cancel(self) -> None:
        self.cancels += 1

    def record_api_error(self) -> None:
        self.api_errors += 1

    def add_metric(self, key: str, value: float) -> None:
        self.custom[key] = self.custom.get(key, 0.0) + value

    def snapshot(self) -> Mapping[str, Any]:
        return {
            "trades": self.trades,
            "wins": self.wins,
            "losses": self.losses,
            "win_rate": self._win_rate(),
            "cancels": self.cancels,
            "api_errors": self.api_errors,
            "custom": dict(self.custom),
        }

    def _win_rate(self) -> Optional[float]:
        if self.trades == 0:
            return None
        return self.wins / self.trades


__all__ = ["JsonFormatter", "MetricsRecorder", "get_json_logger"]
