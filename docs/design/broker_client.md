# broker_client 設計（詳細）

## スコープと役割
- Hyperliquid本番向けの発注/キャンセル/ステータス取得クライアント。
- シリアライズと署名は SDK（`hyperliquid-python-sdk`）に委譲し、リクエスト生成とエラー/リトライ/バリデーションを担う。
- 対象はBTCパーペチュアル単一（assetIndex=0, szDecimals=5, maxLeverage=40, marginTableId=56 取得済み）。

## 依存・前提
- Python 3.11+
- SDK: `hyperliquid-python-sdk`（署名のみ利用）をバージョン固定。
- HTTPクライアント: `httpx` (sync/asyncどちらか決定、デフォルトはsync想定)。
- 環境: 本番のみ (`https://api.hyperliquid.xyz`, `wss://api.hyperliquid.xyz/ws`)。
- 鍵: APIウォレット(agent)秘密鍵を `.env: HL_AGENT_PRIVATE_KEY` で取得。マスター鍵は使用しない。

## 設定項目（env/env.yaml）
- `api_base`, `ws_base`
- `taker_fee_pct`, `maker_fee_pct`（現状 taker 0.045%, maker 0.015%）
- `slippage_model`（初期 5bps, BTで調整）
- 秘匿: `HL_AGENT_PRIVATE_KEY`, `SLACK_WEBHOOK_URL` など

## エンドポイント
- Exchange (`POST /exchange`): `order`, `cancel`, `cancelByCloid`, `scheduleCancel`, `modify`, `noop`
- Info (`POST /info`): `orderStatus`

## インタフェース案（sync想定）
- `place_order(order: OrderParams, grouping="na") -> OrderResult`
- `cancel(asset_index: int, oid: int) -> CancelResult`
- `cancel_by_cloid(asset_index: int, cloid: str) -> CancelResult`
- `schedule_cancel(time_ms: Optional[int]) -> ScheduleResult`
- `modify(oid_or_cloid, new_order: OrderParams) -> ModifyResult`
- `noop() -> None`（nonce消費のみ）
- `get_order_status(user: str, oid: Optional[int], cloid: Optional[str]) -> OrderStatus`

※ async版を作る場合は `AsyncBrokerClient` で同じI/F。

### OrderParams（例）
- `side: "buy"|"sell"`（内部では isBuy bool）
- `price: Decimal|None`（Market時 None or "0"）
- `size: Decimal`（Coin単位、szDecimals=5で丸め）
- `tif: "Gtc"|"Alo"|"Ioc"`（limit時）
- `trigger: Optional[{isMarket: bool, triggerPx: str, tpsl: "tp"|"sl"}]`
- `reduce_only: bool`
- `cloid: Optional[str]`（16バイトhex）

## バリデーション
- tick/lot: priceは有効桁（perpはMAX_DECIMALS=6, szDecimals=5で小数点1桁まで）、sizeは szDecimals=5 で丸め。
- 最小ノーション: 10 USD未満ならエラーを事前検出。
- reduceOnly: 逆方向や増加につながる場合は送信前に拒否。
- OI/角度チェックはサーバ依存のためレスポンスエラー処理で対応。

## 署名・nonce
- SDKの `sign_user_signed_action` を使用。
- nonceはmsタイムスタンプを基本、100件のウィンドウ制約に収まるよう連続昇順を維持。衝突防止にプロセス内でロック管理。
- expiresAfterはデフォルト未設定（レート5倍消費のため）。必要時のみ指定。

## リトライ/バックオフ
- 一時的エラー（429, 5xx, ネットワーク系）は指数バックオフ＋最大試行回数（例3回）。
- 永続エラー（tick不正/MinTradeNtl/ReduceOnly/BadAloPxなど）は即時失敗。
- レートリミット時はレスポンス/ヘッダに従い待機、Circuit Breakerでクールダウン。

## レスポンス処理
- batched statusesは要求配列長と突き合わせ、エラーを位置付きで返す。
- orderStatusのステータスは infoドキュメントの一覧をenum化。
- 主要エラーは `hyperliquid_error_responses.md` にマップしてハンドリング。

## ログ/メトリクス
- ログ: level, event, env, order_id/cloid, side, price, size, reason、latency_ms、api_error（あれば）。
- メトリクス: 成功率、平均/分散のlatency、エラー種別カウント、キャンセル成功率。
- 通知: 致命的エラー（連続失敗、署名失敗、レート超過での停止）時は Slack `#notice-btc-range-scalping` へ。

## 依存先とのI/F
- `strategy_core` → `broker_client.place_order` / `cancel` などを呼ぶ。
- `data_provider` からはマーケットデータのみ。`broker_client` 側ではマーケットデータ取得は行わない（Infoは最低限のみ）。

## TODO（実装時に確定）
- sync/asyncどちらで実装するか（両方必要なら共通基盤を切る）。
- modify対応の要否（必要ならI/Fを有効化）。
- grouping: `normalTpsl` / `positionTpsl` を使う運用方針の確定。
- Circuit Breakerの閾値（連続失敗回数、クールダウン秒）。
