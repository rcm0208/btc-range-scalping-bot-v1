# Rate limits and user limits（Bot運用で重要な部分）

## IPベース（per IP）
- REST: 1200 weight/min。`exchange`は `1 + floor(batch_len/40)`。`l2Book, allMids, clearinghouseState, orderStatus, spotClearinghouseState, exchangeStatus` は weight 2。その他 `info` は weight 20。`userFills/userFillsByTime/fundingHistory/userFunding/...` は返却件数20ごとに加重（大量取得は注意）。
- WebSocket: 接続100、購読1000、ユーザ固有購読ユーザ数10、送信2000メッセージ/分、inflight post 100。

## アドレスベース（ユーザ単位）
- アクションは累積出来高1 USDCあたり1リクエスト許容。初期バッファ10000リクエスト。レート制限時は10秒に1回。
- キャンセルは `min(limit + 100000, limit * 2)` まで緩和（アクション制限でもキャンセルは通しやすい）。
- オープン注文上限: 1000 + 5M USDC出来高ごとに+1、最大5000。上限付近ではRO/トリガー注文は拒否。
- バッチ注文/キャンセル: IPレートは1リクエストだが、アドレスレートは要素数nとしてカウント。

## 運用メモ
- 大量データ取得はWSを優先。RESTでの大量ヒストリカル取得はweight増に注意。
- 高混雑時はブロックスペース利用制限（makerシェア比例）があるため、重複キャンセル送信を避け、WSの結果を信頼する。
