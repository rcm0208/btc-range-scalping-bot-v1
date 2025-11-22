# logging & metrics 設計（ドラフト）

ここに構造化ログ形式、メトリクス一覧、保存先、可観測性の方針を記載する。

## 提案（暫定）
- 出力先: 標準出力に JSON Lines（開発/BT/Live共通）。ファイル保存はオプション。
- ログキー（最低限）:
  - `timestamp`, `level`, `module`, `event`, `env`(bt/live), `symbol`
  - `order_id`/`cloid`(あれば), `side`, `size`, `price`, `reason`(signal/skip理由)
  - `pnl`, `fee`, `latency_ms`(API往復), `error_code`/`api_error`(APIエラー時)
  - `regime`(range_on/off), `cooldown_remaining`, `losing_streak`（運用時の安全系確認用）
- メトリクス（集計単位: セッション/日/期間別）:
  - 勝率、PF、最大DD、平均保持時間、平均/分散のR/R
  - 手数料総額、スリッページ推定、fillレイテンシ（WS/HTTP差）
  - シグナル数、約定数、キャンセル成功率、レートリミット発生回数
- 通知: Slack `#notice-btc-range-scalping`
  - イベント: オープン/クローズ、TP/SL/時間切れ、エラー重大系、緊急停止/連敗ストップ発動
  - フォーマット例: {env, symbol, side, qty, entry_px/exit_px, reason, pnl, fee, ts}

## モジュール別ログ指針
- data_provider: WS再接続、欠損バー、フォールバック実行をINFO/WARNで出力。
- indicator_engine: NaN/Inf検出やウォームアップ不足をWARNで出力（頻発時は抑制）。
- strategy_core: シグナル発生・スキップ理由をDEBUG/INFO、閾値や指標値をcontextで出力。
- risk_manager: 拒否理由（cooldown/連敗/日次損失/既存ポジ）をINFO/WARNで出力。停止発動時はERROR/Slack。
- broker_client: リクエスト/レスポンスの概要（order_id, status, latency）。永続エラーはERROR、一時エラーはWARNとリトライ情報。
- backtester: パラメータセットと結果要約（PF/DD/勝率）。データ欠損はWARN。
- runner: モード開始/終了、緊急停止発動をINFO/ERROR。

## メトリクス詳細（例）
- トレード: 勝率, PF, 最大DD, 平均R/R, 平均保持時間, 手数料, スリッページ。
- パフォーマンス: API往復latencyのp50/p95、WSレイテンシ（イベント受信時刻との差）。
- 動作: シグナル発生数, 約定数, キャンセル成功率, レートリミット発生回数。
- 安全系: 緊急停止発動回数, 連敗ストップ発動回数, 日次損失ストップ発動回数。

## 保存・集計
- 開発/BT: 標準出力JSONをファイルにリダイレクト可能。
- Live: 標準出力JSONをログ収集基盤に送る前提（クラウド移行時にFluent/CloudWatch等を想定）。

## TODO（実装時）
- ログ抑制ポリシー（特にインジ計算のWARN頻度）。
- メトリクス出力形式（CSV/JSON/Prometheusテキストなど）と集計ユーティリティの実装。
