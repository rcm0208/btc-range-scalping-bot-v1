from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Mapping, NotRequired, Optional, TypedDict

Timeframe = Literal["1m", "15m"]
Side = Literal["long", "short"]
SignalType = Literal["enter", "exit", "hold", "skip"]


class Bar(TypedDict):
    """OHLCV バー。ms は UTC 基準。"""

    open: float
    high: float
    low: float
    close: float
    volume: float
    start_ms: int
    end_ms: int
    symbol: str
    timeframe: Timeframe


class Indicators(TypedDict):
    """indicator_engine から返却される最新指標セット。値が未計算の場合は None。"""

    vwap: Optional[float]
    bb_upper: Optional[float]
    bb_middle: Optional[float]
    bb_lower: Optional[float]
    rsi: Optional[float]
    adx: Optional[float]
    ema50: Optional[float]
    ema200: Optional[float]
    atr: Optional[float]


class Signal(TypedDict):
    """strategy_core の判定結果。enter/exit/hold/skip を表現。"""

    type: SignalType
    side: Optional[Side]
    reason: str
    tp_level: Optional[float]
    sl_level: Optional[float]
    timeout_ms: Optional[int]
    context: Optional[Mapping[str, Any]]


class CheckResult(TypedDict, total=False):
    """risk_manager による可否判定。"""

    allowed: bool
    reason: NotRequired[str]


class PnlStats(TypedDict):
    """risk_manager 判定用の損益・状態情報。"""

    open_positions: int
    daily_realized_pct: float
    last_close_time: Optional[datetime]
    losing_streak: int


__all__ = [
    "Bar",
    "Indicators",
    "Signal",
    "CheckResult",
    "PnlStats",
    "Side",
    "SignalType",
    "Timeframe",
]
