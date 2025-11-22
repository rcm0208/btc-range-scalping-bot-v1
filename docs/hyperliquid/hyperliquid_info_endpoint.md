# Info endpoint（Bot で使用する部分のみ抜粋）

共通:

- エンドポイント: `POST https://api.hyperliquid.xyz/info`
- ヘッダ: `Content-Type: application/json`
- 対象: 今回は BTC パーペチュアルのみ（spot 系は不要）。`coin` は `meta` の `universe` 名（例: "BTC"）。
- ページネーション: 時系列系は 1 リクエスト最大 500 件または 2000 件。必要に応じて最後のタイムスタンプを次の `startTime` に設定して再取得。

## allMids（全銘柄の Mid 取得）

リクエスト:

```json
{ "type": "allMids", "dex": "" }
```

レスポンス例:

```json
{ "BTC": "29792.0" }
```

## openOrders（ユーザの未約定注文）

リクエスト:

```json
{ "type": "openOrders", "user": "<0x...address>", "dex": "" }
```

レスポンス例:

```json
[{ "coin": "BTC", "limitPx": "29792.0", "oid": 91490942, "side": "A", "sz": "0.0", "timestamp": 1681247412573 }]
```

### frontendOpenOrders（追加情報付き）

リクエスト:

```json
{ "type": "frontendOpenOrders", "user": "<0x...address>", "dex": "" }
```

レスポンス例:

```json
[{ "coin": "BTC", "orderType": "Limit", "limitPx": "29792.0", "origSz": "5.0", "sz": "5.0", "side": "A", "reduceOnly": false, "isPositionTpsl": false, "isTrigger": false, "triggerPx": "0.0", "triggerCondition": "N/A", "oid": 91490942, "timestamp": 1681247412573 }]
```

## userFills（最新 2000 件）

リクエスト:

```json
{ "type": "userFills", "user": "<0x...address>", "aggregateByTime": false }
```

レスポンス例（Perp のみ抜粋）:

```json
[{ "coin": "BTC", "dir": "Open Long", "px": "18435.0", "sz": "1.0", "side": "B", "time": 1681222254710, "oid": 90542681, "fee": "0.01", "feeToken": "USDC", "tid": 118906512037719, "closedPnl": "0.0", "crossed": false, "startPosition": "26.86" }]
```

## userFillsByTime（時間範囲指定・最大 2000 件/リクエスト）

リクエスト:

```json
{ "type": "userFillsByTime", "user": "<0x...address>", "startTime": 1681222254000, "endTime": 1681223254000, "aggregateByTime": false }
```

## userRateLimit（API 使用量）

リクエスト:

```json
{ "type": "userRateLimit", "user": "<0x...address>" }
```

レスポンス例:

```json
{ "cumVlm": "2854574.593578", "nRequestsUsed": 2890, "nRequestsCap": 2864574, "nRequestsSurplus": 0 }
```

## orderStatus（oid または cloid で注文状態取得）

リクエスト:

```json
{ "type": "orderStatus", "user": "<0x...address>", "oid": 1 }
```

主なステータス:

- `open`: 発注済み
- `filled`: 全量約定
- `canceled`: ユーザキャンセル
- `rejected`: 受付失敗
- `marginCanceled` / `perpMarginRejected`: 証拠金不足
- `reduceOnlyCanceled` / `reduceOnlyRejected`: RO 条件不一致
- `tickRejected`: ティック不正
- `minTradeNtlRejected`: 最小ノーション未達
- `badAloPxRejected`: Post-only が即クロス
- `iocCancelRejected`: IOC が約定できず
- `marketOrderNoLiquidityRejected`: 板流動性不足
- `positionIncreaseAtOpenInterestCapRejected` など OI 制約系

レスポンス例:

```json
{ "status": "order", "order": { "order": { "coin": "BTC", "side": "A", "limitPx": "2412.7", "sz": "0.0", "oid": 1, "timestamp": 1724361546645, "orderType": "Market", "origSz": "0.0076", "tif": "FrontendMarket", "cloid": null }, "status": "filled", "statusTimestamp": 1724361546645 } }
```

## l2Book（板スナップショット：最大 20 レベル/サイド）

リクエスト:

```json
{ "type": "l2Book", "coin": "BTC", "n": 20, "dex": "" }
```

用途: 現在価格の近傍確認やスリッページモデルのために使用。

## candleSnapshot（最新最大 5000 本）

- エンドポイント: `POST https://api.hyperliquid.xyz/info`
- 対応 interval: "1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "8h", "12h", "1d", "3d", "1w", "1M"

リクエスト:

```json
{
  "type": "candleSnapshot",
  "req": {
    "coin": "BTC",
    "interval": "15m",
    "startTime": 1681923600000,
    "endTime": 1681924500000
  }
}
```

レスポンス例:

```json
[
  {
    "T": 1681924499999,
    "c": "29258.0",
    "h": "29309.0",
    "i": "15m",
    "l": "29250.0",
    "n": 189,
    "o": "29295.0",
    "s": "BTC",
    "t": 1681923600000,
    "v": "0.98639"
  }
]
```

---

削除したセクション: subAccounts, vaults, portfolio 履歴、referral、fees、staking、HIP-3、alignedQuoteToken など、今回の Perp Bot には不要なもの。必要になった場合に再取得する。
