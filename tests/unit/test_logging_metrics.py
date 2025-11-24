from __future__ import annotations

import json
import logging
from io import StringIO

from src.infra.logging_metrics import JsonFormatter, MetricsRecorder, get_json_logger


def test_json_logger_emits_standard_keys() -> None:
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())

    base_logger = logging.getLogger("test_json_logger_emits_standard_keys")
    base_logger.handlers.clear()
    base_logger.addHandler(handler)
    base_logger.setLevel(logging.INFO)

    logger = get_json_logger("test_json_logger_emits_standard_keys", env="bt")
    logger.info("hello", extra={"event": "test_event", "symbol": "BTC"})

    output = stream.getvalue().strip()
    data = json.loads(output)
    for key in ("timestamp", "level", "module", "event", "env", "message"):
        assert key in data
    assert data["env"] == "bt"
    assert data["event"] == "test_event"
    assert data["symbol"] == "BTC"


def test_get_json_logger_reuses_handler_and_sets_env() -> None:
    logger1 = get_json_logger("logger_reuse", env="bt")
    logger2 = get_json_logger("logger_reuse", env="bt")
    assert logger1.logger is logger2.logger  # type: ignore[attr-defined]


def test_metrics_recorder_snapshot_and_win_rate() -> None:
    metrics = MetricsRecorder()
    metrics.record_trade(is_win=True)
    metrics.record_trade(is_win=False)
    metrics.record_trade(is_win=None)
    metrics.record_cancel()
    metrics.record_api_error()
    metrics.add_metric("latency_ms", 100.0)
    metrics.add_metric("latency_ms", 50.0)

    snap = metrics.snapshot()
    assert snap["trades"] == 3
    assert snap["wins"] == 1
    assert snap["losses"] == 1
    assert snap["win_rate"] == 1 / 3
    assert snap["cancels"] == 1
    assert snap["api_errors"] == 1
    assert snap["custom"]["latency_ms"] == 150.0
