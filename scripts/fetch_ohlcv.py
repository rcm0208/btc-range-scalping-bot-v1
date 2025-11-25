from __future__ import annotations

import argparse
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import httpx
import pyarrow as pa
import pyarrow.parquet as pq


def parse_dt(value: str) -> datetime:
    """Parse ISO8601 into aware UTC datetime."""
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    elif dt.tzinfo != timezone.utc:
        raise ValueError("datetime must be UTC")
    return dt


def fetch_klines(
    *,
    client: httpx.Client,
    api_base: str,
    symbol: str,
    interval: str,
    start_ms: int,
    end_ms: int,
) -> List[Dict[str, Any]]:
    """Fetch klines from Binance-like API and return list of rows."""
    rows: List[Dict[str, Any]] = []
    cursor = start_ms
    while cursor < end_ms:
        params = {
            "symbol": symbol,
            "interval": interval,
            "startTime": cursor,
            "endTime": end_ms,
            "limit": 1000,
        }
        resp = client.get(f"{api_base}/api/v3/klines", params=params, timeout=10.0)
        resp.raise_for_status()
        data = resp.json()
        if not data:
            break
        for entry in data:
            open_time = int(entry[0])
            close_time = int(entry[6])
            rows.append(
                {
                    "open": float(entry[1]),
                    "high": float(entry[2]),
                    "low": float(entry[3]),
                    "close": float(entry[4]),
                    "volume": float(entry[5]),
                    "start_ms": open_time,
                    "end_ms": close_time,
                }
            )
        cursor = int(data[-1][6]) + 1
        # Avoid hitting rate limits too hard
        time.sleep(0.2)
    return rows


def to_parquet(rows: List[Dict[str, Any]], *, symbol: str, timeframe: str, output: Path) -> None:
    if not rows:
        raise ValueError(f"No rows fetched for timeframe {timeframe}")
    for row in rows:
        row["symbol"] = symbol
        row["timeframe"] = timeframe
    table = pa.Table.from_pylist(rows)
    output.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, output)


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch OHLCV and save as parquet.")
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--start", required=True, help="ISO8601 UTC start, e.g. 2024-01-01T00:00:00Z")
    parser.add_argument("--end", required=True, help="ISO8601 UTC end")
    parser.add_argument("--api-base", default="https://api.binance.com")
    parser.add_argument("--out-1m", default="data/ohlcv_1m.parquet")
    parser.add_argument("--out-15m", default="data/ohlcv_15m.parquet")
    args = parser.parse_args()

    start_dt = parse_dt(args.start)
    end_dt = parse_dt(args.end)
    if start_dt >= end_dt:
        raise SystemExit("start must be earlier than end")
    start_ms = int(start_dt.timestamp() * 1000)
    end_ms = int(end_dt.timestamp() * 1000)

    with httpx.Client() as client:
        rows_1m = fetch_klines(
            client=client,
            api_base=args.api_base,
            symbol=args.symbol,
            interval="1m",
            start_ms=start_ms,
            end_ms=end_ms,
        )
        rows_15m = fetch_klines(
            client=client,
            api_base=args.api_base,
            symbol=args.symbol,
            interval="15m",
            start_ms=start_ms,
            end_ms=end_ms,
        )

    to_parquet(rows_1m, symbol=args.symbol, timeframe="1m", output=Path(args.out_1m))
    to_parquet(rows_15m, symbol=args.symbol, timeframe="15m", output=Path(args.out_15m))


if __name__ == "__main__":
    main()
