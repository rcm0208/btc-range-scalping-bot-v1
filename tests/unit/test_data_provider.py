from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from src.infra.data_provider import DataProvider, MissingColumnsError

REQUIRED_COLUMNS = [
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


def _write_parquet(path, rows) -> None:
    table = pa.table({col: [row[col] for row in rows] for col in REQUIRED_COLUMNS})
    pq.write_table(table, path)


def test_load_ohlcv_filters_and_orders(tmp_path) -> None:
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    bars = []
    for i in range(3):
        start_ms = int((start + timedelta(minutes=i)).timestamp() * 1000)
        bars.append(
            {
                "open": 100.0 + i,
                "high": 101.0 + i,
                "low": 99.0 + i,
                "close": 100.5 + i,
                "volume": 10.0 + i,
                "start_ms": start_ms,
                "end_ms": start_ms + 60_000,
                "symbol": "BTC",
                "timeframe": "1m",
            }
        )

    # 異なるタイムフレームはフィルタされる
    tf15_start = int(start.timestamp() * 1000)
    bars.append(
        {
            "open": 200.0,
            "high": 201.0,
            "low": 199.0,
            "close": 200.5,
            "volume": 20.0,
            "start_ms": tf15_start,
            "end_ms": tf15_start + 900_000,
            "symbol": "BTC",
            "timeframe": "15m",
        }
    )

    path = tmp_path / "ohlcv_1m.parquet"
    _write_parquet(path, bars)

    provider = DataProvider({"1m": str(path)})
    end = start + timedelta(minutes=3)
    loaded = list(provider.load_ohlcv("1m", start, end))

    assert [bar["start_ms"] for bar in loaded] == sorted(
        [bar["start_ms"] for bar in bars if bar["timeframe"] == "1m"]
    )
    assert all(bar["timeframe"] == "1m" for bar in loaded)
    assert all(bar["symbol"] == "BTC" for bar in loaded)


def test_load_ohlcv_warns_on_gap(tmp_path, caplog) -> None:
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    start_ms = int(start.timestamp() * 1000)
    gap_start_ms = int((start + timedelta(minutes=2)).timestamp() * 1000)
    bars = [
        {
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.5,
            "volume": 10.0,
            "start_ms": start_ms,
            "end_ms": start_ms + 60_000,
            "symbol": "BTC",
            "timeframe": "1m",
        },
        {
            "open": 102.0,
            "high": 103.0,
            "low": 101.0,
            "close": 102.5,
            "volume": 11.0,
            "start_ms": gap_start_ms,
            "end_ms": gap_start_ms + 60_000,
            "symbol": "BTC",
            "timeframe": "1m",
        },
    ]
    path = tmp_path / "ohlcv_gap.parquet"
    _write_parquet(path, bars)

    provider = DataProvider({"1m": str(path)})
    with caplog.at_level(logging.WARNING, logger="src.infra.data_provider"):
        loaded = list(provider.load_ohlcv("1m", start, start + timedelta(minutes=3)))

    assert len(loaded) == 2
    assert any("Missing 1m bar detected" in record.message for record in caplog.records)


def test_load_ohlcv_missing_columns_raises(tmp_path) -> None:
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    start_ms = int(start.timestamp() * 1000)
    table = pa.table(
        {
            "open": [100.0],
            "high": [101.0],
            "low": [99.0],
            "close": [100.5],
            # volume をあえて欠落させる
            "start_ms": [start_ms],
            "end_ms": [start_ms + 60_000],
            "symbol": ["BTC"],
            "timeframe": ["1m"],
        }
    )
    path = tmp_path / "ohlcv_missing.parquet"
    pq.write_table(table, path)

    provider = DataProvider({"1m": str(path)})
    with pytest.raises(MissingColumnsError):
        list(provider.load_ohlcv("1m", start, start + timedelta(minutes=1)))


def test_stream_bars_not_implemented(tmp_path) -> None:
    provider = DataProvider({"1m": str(tmp_path / "noop.parquet")})

    async def consume() -> None:
        await provider.stream_bars("1m")

    with pytest.raises(NotImplementedError):
        import asyncio

        asyncio.run(consume())
