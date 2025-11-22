# Perpetuals info（Botで使用する部分のみ抜粋）

共通:
- エンドポイント: `POST https://api.hyperliquid.xyz/info`
- ヘッダ: `Content-Type: application/json`
- dex: 未指定はデフォルトのperp dex。BTCパーペチュアルのみを想定。

## perpDexs（必要時のみ）
全perp dex一覧。通常はデフォルトdex固定のため利用頻度は低い。
```json
{ "type": "perpDexs" }
```

## meta（必須）
銘柄定義・桁数・レバレッジ・マージンテーブル取得。`universe` から `szDecimals` や `maxLeverage` を参照し、tick/lot検証に利用。
```json
{ "type": "meta", "dex": "" }
```
レスポンス例（抜粋）:
```json
{
  "universe": [ { "name": "BTC", "szDecimals": 5, "maxLeverage": 40, "assetIndex": 0 } ],
  "marginTables": [ [56, { "marginTiers": [ { "lowerBound": "0.0", "maxLeverage": 40 }, { "lowerBound": "150000000.0", "maxLeverage": 20 } ] }] ]
}
```

## metaAndAssetCtxs（推奨: 価格/資産コンテキストをまとめて取得）
`meta` と併せてmark/mid/oi/funding等を取得。バックテスト・シミュレーションの初期化や稼働前チェックに有用。
```json
{ "type": "metaAndAssetCtxs" }
```
レスポンス例（抜粋）:
```json
[ { "universe": [ { "name": "BTC", "szDecimals": 5, "maxLeverage": 40 } ] },
  [ { "markPx": "...", "midPx": "...", "openInterest": "...", "funding": "..." } ]
]
```

## clearinghouseState（必須）
口座サマリ・建玉・証拠金使用状況。
```json
{ "type": "clearinghouseState", "user": "<0x...address>", "dex": "" }
```
レスポンス例（抜粋）:
```json
{
  "assetPositions": [
    { "position": { "coin": "BTC", "entryPx": "2986.3", "szi": "0.0335",
        "unrealizedPnl": "-0.0134", "marginUsed": "4.967826", "liquidationPx": "2866.2693" },
      "type": "oneWay" }
  ],
  "marginSummary": { "accountValue": "13109.48", "totalMarginUsed": "4.967826", "totalNtlPos": "100.02765" },
  "withdrawable": "13104.514502"
}
```

## userFunding / userNonFundingLedgerUpdates（必要時のみ）
資金調達履歴や入出金履歴。分析・監査用途。通常のシグナリング・執行には必須ではない。
```json
{ "type": "userFunding", "user": "<0x...>", "startTime": 0, "endTime": 0 }
```

## fundingHistory（必要時のみ）
過去のファンディング率。バックテストやスリッページ/コスト評価で使う場合のみ。
```json
{ "type": "fundingHistory", "coin": "BTC", "startTime": 0, "endTime": 0 }
```

## predictedFundings（任意）
他取引所含むファンディング予測。裁定/コスト見積もりをする場合のみ使用。
```json
{ "type": "predictedFundings" }
```

## perpsAtOpenInterestCap（任意）
OI上限に達している銘柄一覧。板状況チェックに利用可能だが、BTC単独運用では頻度低。
```json
{ "type": "perpsAtOpenInterestCap" }
```

## activeAssetData（任意）
ユーザごとの建玉可能サイズなど。レバ調整や発注前チェックを細かく行う場合に利用。
```json
{ "type": "activeAssetData", "user": "<0x...>", "coin": "BTC" }
```

---
削除したセクション: vault/portfolio/spot/auction/builder perp用のlimit/statusなど、今回のBTCパーペチュアルBot実装に不要なもの。必要になれば再取得する。
