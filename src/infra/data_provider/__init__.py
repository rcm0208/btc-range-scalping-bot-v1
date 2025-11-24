from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncIterator, Dict, Iterator, Mapping, Optional, Sequence

import pyarrow.parquet as pq

from src.utils import Bar, Timeframe

logger = logging.getLogger(__name__)

_TIMEFRAME_TO_MS: Dict[Timeframe, int] = {
    "1m": 60_000,
    "15m": 900_000,
}

_REQUIRED_COLUMNS = [
    "open",
    "high",
    "low",
    "close",
    "volume",
    "start_ms",
    "end_ms",
    "symbol",
    "timeframe",
]


class MissingColumnsError(ValueError):
    """Parquet に必要なカラムが不足している場合の例外。"""


class DataProvider:
    """Parquet 読み出しと WS 購読 I/F の雛形。"""

    def __init__(self, timeframe_paths: Mapping[Timeframe, str]) -> None:
        if not timeframe_paths:
            raise ValueError("timeframe_paths must not be empty")
        self.timeframe_paths = {tf: Path(path) for tf, path in timeframe_paths.items()}

    def load_ohlcv(
        self,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
    ) -> Iterator[Bar]:
        """指定範囲のOHLCVをParquetから読み出す。

        Args:
            timeframe: 読み出す足（1m/15m）
            start: 取得開始時刻（UTC想定）
            end: 取得終了時刻（UTC想定）

        Yields:
            Bar: フィルタ済みかつ start_ms 昇順のバー
        """
        self._ensure_supported_timeframe(timeframe)
        path = self._get_path(timeframe)
        start_ms = _to_timestamp_ms(start)
        end_ms = _to_timestamp_ms(end)
        if end_ms <= start_ms:
            raise ValueError("end must be after start")

        table = self._read_parquet(path)
        data = self._select_required_columns(table, path)
        rows = self._filter_rows(data, timeframe, start_ms, end_ms)
        if not rows:
            return

        expected_step = _TIMEFRAME_TO_MS[timeframe]
        first_start = rows[0]["start_ms"]
        if first_start > start_ms:
            self._log_gap(
                timeframe=timeframe,
                expected_start=start_ms,
                actual_start=first_start,
                reason="start_gap",
            )

        prev_start: Optional[int] = None
        for row in rows:
            current_start = row["start_ms"]
            if prev_start is not None and current_start != prev_start + expected_step:
                self._log_gap(
                    timeframe=timeframe,
                    expected_start=prev_start + expected_step,
                    actual_start=current_start,
                    reason="missing_bar",
                )
            prev_start = current_start
            yield row

    async def stream_bars(self, timeframe: Timeframe) -> AsyncIterator[Bar]:
        """Hyperliquid candle 購読用のプレースホルダ。

        docs/hyperliquid/hyperliquid_websocket.md の candle サブスクリプション
        `{ "type": "candle", "coin": "BTC", "interval": "1m" | "15m" }` を想定。
        """
        self._ensure_supported_timeframe(timeframe)
        raise NotImplementedError("WebSocket streaming is not implemented yet.")

    def _ensure_supported_timeframe(self, timeframe: Timeframe) -> None:
        if timeframe not in _TIMEFRAME_TO_MS:
            raise ValueError(f"Unsupported timeframe: {timeframe}")

    def _get_path(self, timeframe: Timeframe) -> Path:
        try:
            return self.timeframe_paths[timeframe]
        except KeyError as exc:
            raise ValueError(f"No parquet path configured for timeframe {timeframe}") from exc

    def _read_parquet(self, path: Path):
        if not path.exists():
            raise FileNotFoundError(f"Parquet file not found: {path}")
        return pq.read_table(path)

    def _select_required_columns(self, table, path: Path) -> Mapping[str, Sequence]:
        missing = [col for col in _REQUIRED_COLUMNS if col not in table.column_names]
        if missing:
            raise MissingColumnsError(f"Missing columns {missing} in {path}")
        return table.select(_REQUIRED_COLUMNS).to_pydict()

    def _filter_rows(
        self,
        data: Mapping[str, Sequence],
        timeframe: Timeframe,
        start_ms: int,
        end_ms: int,
    ) -> list[Bar]:
        rows: list[Bar] = []
        total = len(data["start_ms"])
        for idx in range(total):
            tf = str(data["timeframe"][idx])
            if tf != timeframe:
                continue
            bar_start = int(data["start_ms"][idx])
            bar_end = int(data["end_ms"][idx])
            if bar_start < start_ms or bar_end > end_ms:
                continue
            bar: Bar = {
                "open": float(data["open"][idx]),
                "high": float(data["high"][idx]),
                "low": float(data["low"][idx]),
                "close": float(data["close"][idx]),
                "volume": float(data["volume"][idx]),
                "start_ms": bar_start,
                "end_ms": bar_end,
                "symbol": str(data["symbol"][idx]),
                "timeframe": timeframe,
            }
            rows.append(bar)
        rows.sort(key=lambda b: b["start_ms"])
        return rows

    def _log_gap(
        self,
        timeframe: Timeframe,
        expected_start: int,
        actual_start: int,
        reason: str,
    ) -> None:
        logger.warning(
            "Missing %s bar detected (reason=%s, expected_start_ms=%s, actual_start_ms=%s, expected_time=%s, actual_time=%s)",
            timeframe,
            reason,
            expected_start,
            actual_start,
            _format_ms(expected_start),
            _format_ms(actual_start),
        )


def _to_timestamp_ms(dt: datetime) -> int:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def _format_ms(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat()


__all__ = ["DataProvider", "MissingColumnsError"]
