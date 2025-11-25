from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Mapping, NotRequired, Optional, TypedDict

Timeframe = Literal["1m", "15m", "1h", "4h"]
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
    stoch_rsi_k: Optional[float]
    stoch_rsi_d: Optional[float]
    adx: Optional[float]
    ema50: Optional[float]
    ema200: Optional[float]
    atr: Optional[float]
    ha_open: Optional[float]
    ha_close: Optional[float]
    ha_high: Optional[float]
    ha_low: Optional[float]


class Signal(TypedDict):
    """strategy_core の判定結果。enter/exit/hold/skip を表現。"""

    type: SignalType
    side: Optional[Side]
    reason: str
    tp_level: Optional[float]
    sl_level: Optional[float]
    timeout_ms: Optional[int]
    tp1_level: Optional[float]
    trailing_start: Optional[float]
    context: Optional[Mapping[str, Any]]


class CheckResult(TypedDict):
    """risk_manager による可否判定。"""

    allowed: bool
    reason: Optional[str]


class PnlStats(TypedDict):
    """risk_manager 判定用の損益・状態情報。"""

    open_positions: int
    daily_realized_pct: float
    last_close_time: Optional[datetime]
    losing_streak: int


class OpenPosition(TypedDict):
    """strategy_core が exit 判定に用いるシンプルなポジション情報。"""

    side: Side
    entry_price: float
    entry_time_ms: int
    tp_level: float  # 主TP (TP2)
    tp1_level: Optional[float]  # 部分利確用TP1
    sl_level: float
    timeout_ms: int
    filled_tp1: bool
    trailing_active: bool
    trailing_start: Optional[float]


__all__ = [
    "Bar",
    "Indicators",
    "Signal",
    "CheckResult",
    "PnlStats",
    "Side",
    "SignalType",
    "Timeframe",
    "OpenPosition",
]
