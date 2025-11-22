# data_provider 設計（ドラフト）

ここにOHLCV取得（ヒストリカル・ライブ）とWS購読の設計を記載する。

## 方針（暫定）
- ヒストリカル: バックテスト用のみ取得・保存。ローカル完結（DBなし）。形式はParquet（圧縮: snappy）を推奨。
  - 1分足・15分足を保持。パス例: `data/ohlcv_1m.parquet`, `data/ohlcv_15m.parquet`
  - 取得元: Hyperliquid API（info/candle または candleSnapshot があれば優先）。Hyperliquid固有のため公式APIを基本とする。
- ライブ: WSを主、RESTフォールバック（切断時のみ）。
  - 購読チャネル: `candle` 1m/15m, `orderUpdates`, `userEvents`, 必要に応じて `bbo` or `l2Book`。
  - データ供給I/F: `get_ohlcv(symbol, timeframe, start, end)`（イテレータ）と `stream_bars(timeframe)`（async generator想定）を後で定義。
- レート/リトライ: IP/アドレス制限を意識し、RESTは再試行＋バックオフ、WSは自動再接続＋遅延購読。
- キャッシュ: 直近バーはメモリ保持。ヒストリカルはParquetから再利用。

## 役割
- バックテスト用のOHLCV供給（1m/15m）と、ライブ運用時のリアルタイムバー/イベント供給。
- インジケータ計算は `indicator_engine` に委譲し、価格データの整形・整合性チェックを担当。

## インタフェース案
- ヒストリカル
  - `load_ohlcv(timeframe: str, start: datetime, end: datetime) -> Iterator[Bar]`（Parquetからロード、足りない分はAPIで補完）
  - `fetch_and_store(timeframe: str, start: datetime, end: datetime, path: str) -> None`（APIから取得しParquet保存）
- ライブ
  - `stream_bars(timeframe: str) -> AsyncIterator[Bar]`（WS candle購読）
  - `stream_events() -> AsyncIterator[UserEvent]`（orderUpdates/userEventsを集約、必要に応じ分岐）
  - `fallback_rest_last_bar(timeframe: str) -> Optional[Bar]`（WS途絶時の最後のバー取得）

### Bar構造（例）
```
Bar = {
  "open": float,
  "high": float,
  "low": float,
  "close": float,
  "volume": float,
  "start_ms": int,
  "end_ms": int,
  "symbol": str,
  "timeframe": str, # "1m" or "15m"
}
```

## 取得フロー（ヒストリカル）
1. Parquet存在チェック（path指定）。必要範囲が欠損していればAPIで取得し追記（重複はdedup）。
2. APIは時間範囲を分割し、rate limitを考慮して順次取得。最大件数制限（500/2000件）に応じてページング。
3. 読み出し時は `start/end` でフィルタし、タイムスタンプ昇順で返す。

## ライブ購読
- WSチャネル: `candle` ("1m", "15m") を必須購読。`orderUpdates`/`userEvents`は別モジュールで使用するが、ここではバー供給に集中（必要ならイベントもラップ）。
- 再接続: ping/pong監視、60秒メッセージ無なら再接続→購読再送。遅延購読で重複スキップ（isSnapshot使用）。
- フォールバック: WS切断が長引く場合、RESTの `candle` で最新バーをポーリング（頻度はレートリミットに配慮し最小限）。

## バリデーション/整合性
- タイムスタンプ連続性チェック（欠損バーがあれば警告ログ、必要ならギャップ埋めはNaNでマーク）。
- 値域チェック: OHLCの整合性（high/low範囲）、volumeの負値排除。
- Timezone: すべてUTCのmsで扱う。

## レート・リトライ
- REST: 429/5xxは指数バックオフ（例3回）、重量級エンドポイントはインターバル設定。
- WS: 接続失敗/切断時は再接続間隔を指数バックオフ（上限あり）。

## 保存形式
- Parquet (snappy) を推奨。列: timestamp_start, timestamp_end, open, high, low, close, volume, symbol, timeframe。
- ディレクトリ例: `data/ohlcv_1m.parquet`, `data/ohlcv_15m.parquet`

## TODO（決定/実装時）
- `httpx` の sync/async どちらを採用するか（broker_clientとの整合）。
- candle取得APIのエンドポイント詳細（info/candle または candleSnapshot の有無と使い分け）を確定。
- 欠損バーの補間ポリシー（スキップ vs NaN埋め）。
- orderUpdates/userEventsをdata_providerで扱うか、broker_clientや別コンポーネントに分離するか最終決定。
