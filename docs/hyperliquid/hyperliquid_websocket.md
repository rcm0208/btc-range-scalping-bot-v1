# WebSocket（Botで使用する部分のみ抜粋）

エンドポイント:
- Mainnet: `wss://api.hyperliquid.xyz/ws`
- Testnet: `wss://api.hyperliquid-testnet.xyz/ws`

接続・購読:
- 形式: `{ "method": "subscribe", "subscription": { ... } }`
- Ack後に `channel`=subscription type でデータが届く。スナップショットは `isSnapshot: true`。
- 60秒間サーバからのメッセージがないと切断されるため、低頻度チャネルのみの場合は `{ "method": "ping" }` を送る。

Botで主に使う購読チャネル（BTCパーペチュアル想定）:
- `candle`: `{ "type": "candle", "coin": "BTC", "interval": "1m" | "15m" }`（戦略ロジックの1m/15m足）
- `l2Book`: `{ "type": "l2Book", "coin": "BTC" }`（板スナップショット）。必要に応じて `nSigFigs`/`mantissa` で圧縮指定。
- `trades`: `{ "type": "trades", "coin": "BTC" }`（約定ティック。VWAP/ボラ計算補助に使用可）
- `userEvents`: `{ "type": "userEvents", "user": "<address>" }`（fills/funding/liquidation/nonUserCancel がまとまる）
- `orderUpdates`: `{ "type": "orderUpdates", "user": "<address>" }`（注文ステータス変化）
- `userFills`: `{ "type": "userFills", "user": "<address>", "aggregateByTime": false }`（fillsのみを追いたい場合）
- `userFundings`: `{ "type": "userFundings", "user": "<address>" }`（資金調達受払）
- `userNonFundingLedgerUpdates`: `{ "type": "userNonFundingLedgerUpdates", "user": "<address>" }`（入出金/移転など。必要時のみ）

補足チャネル（必要に応じて）:
- `allMids`: 全銘柄mid。BTC専用なら不要。
- `bbo`: ベスト気配のみ。板負荷を抑えたい場合に代替。
- `activeAssetCtx`: `{ "type": "activeAssetCtx", "coin": "BTC" }`（funding/openInterest等）。頻度を要確認。
- `activeAssetData`: `{ "type": "activeAssetData", "user": "<address>", "coin": "BTC" }`（発注可能サイズ等）。高頻度ではない想定。

データ型（抜粋）:
- `WsTrade`: `{ coin, side, px, sz, time, tid, users }`
- `WsBook`: `{ coin, levels: [bids[], asks[]], time }` 各レベルは `{ px, sz, n }`
- `Candle`: `{ t(openMs), T(closeMs), o, c, h, l, v, n }`
- `WsOrder`: `{ order: { coin, side, limitPx, sz, oid, timestamp, origSz, cloid? }, status, statusTimestamp }`
- `WsUserEvent`: `{ fills: WsFill[] } | { funding: WsUserFunding } | { liquidation: WsLiquidation } | { nonUserCancel: WsNonUserCancel[] }`
- `WsFill`: `{ coin, px, sz, side, time, oid, tid, fee, feeToken, crossed, closedPnl, startPosition, dir }`

ポスト（HTTP代替）:
- 形式: `{ "method": "post", "id": <number>, "request": { "type": "info" | "action", "payload": { ... } } }`
- 応答: `{ "channel": "post", "data": { "id": <number>, "response": { "type": "info"|"action"|"error", "payload": { ... } } } }`
- HTTPで十分ならpostは必須ではない。低レイテンシ要件やコネクション集約をしたい場合のみ使用。

削除したセクション:
- webData2, notification, twap系、spot/多銘柄用の詳細、非Bot用途の型説明を省略。必要になれば履歴から復元可能。
