# indicator_engine 設計（詳細）

## 役割
- 1m/15mのOHLCVからインジケータを計算・更新し、strategy_coreに必要な値（VWAP, BB, RSI, ADX, EMA, ATR）を提供する。
- ローリング更新で計算負荷を抑え、バックテストとライブで同一ロジックを使用する。

## 対応インジケータ
- VWAP（1m, 15m）：累積(typical_price*vol)/累積vol。15m VWAPを1mタイムラインにプロット（最新15mバーの値を1mに配布）。
- Bollinger Bands（期間20, 偏差2σ）
- RSI(7)
- ADX(14)
- EMA(50), EMA(200)
- ATR(N)（NはBTで調整。急騰急落フィルタ用）

## 入出力I/F（案）
- `update(timeframe: str, bar: Bar) -> Indicators`（単一バーでローリング更新）
- `get_latest(timeframe: str) -> Indicators`（最新値取得）
- `warmup(timeframe: str, bars: Iterable[Bar]) -> None`（初期ウォームアップ）

### Bar
```
Bar = { open, high, low, close, volume, start_ms, end_ms, symbol, timeframe }
```

### Indicators（例）
```
Indicators = {
  "vwap": float,
  "bb_upper": float, "bb_middle": float, "bb_lower": float,
  "rsi": float,
  "adx": float,
  "ema50": float, "ema200": float,
  "atr": float,
}
```

## 実装方針
- 計算ライブラリ: pandas/numpy + numbaは必要に応じ検討。ローリング窓を自前で保持し差分更新。
- ウィンドウバッファ: 各timeframeごとに deque または固定長配列で価格・TR・typical price を保持。
- VWAP: ロールアップ式で累積量を維持（累積をリセットする期間は設定可、デフォルトはセッション持続）。
- 15m VWAPの1mプロット: 最新の15m VWAPを1m側に注入する形で strategy_core が参照できるようにする。

## エラーハンドリング/検証
- 入力のタイムフレームチェック（"1m"|"15m"のみ）。
- NaN/Infを検出したらログに警告し、前回値を持ち越すかNoneを返す（要設計）。

## パフォーマンス
- 1mごとに全指標を再計算せず、差分更新（EMA, RSI, ADXは前回値利用）。
- バックテスト用の一括計算時はvectorized計算を選択する可能性あり（BTの速度を優先）。

## TODO（実装時に確定）
- ATR期間（N）の確定（初期は20を想定、要BT調整）。
- VWAPリセット条件（デイリーベース vs 継続）を決める。
- NaN処理ポリシー、warmup期間の長さ（最低200本程度を推奨）。
