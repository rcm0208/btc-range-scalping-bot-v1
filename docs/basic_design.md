# BTC Range Scalping Bot v1 基本設計書

## 1. 目的・スコープ

- 目的: 要件定義書の戦略を、実装可能な構成・責務分割・インタフェースに落とし込む。
- スコープ: トレード戦略ロジックとその周辺（データ取得、BT 基盤、通知、運用枠組み）。インフラ詳細は最小限（将来クラウド前提）。

## 2. 全体方針

- 言語/ランタイム: Python 3.11+（豊富な市場データ処理/BT エコシステム、学習コスト低）。
- アーキタイプ: モジュール分離＋疎結合 DI。テスト容易性とパラメータ調整を最優先。
- データ粒度: 1 分足・15 分足を主とし、VWAP/BB/RSI/ADX/EMA 計算用に OHLCV を保持。
- 配置: ローカル/コンテナで開発 → 将来クラウド（ECS/K8s 等）へ移行しやすい構成。本番移行は BT 完了後に極小ロットから段階的に上げる方針。
- コンフィグ: `.env` + `config/*.yaml`（戦略パラメータ、API キー、環境切替 dev/bt/live）。
- ログ/通知: 構造化ログは標準出力 JSON、Slack 通知は `#notice-btc-range-scalping` チャンネルに送信。
- 手数料/スリッページ初期値: taker 0.045%（4.5bps）、maker 0.015%（1.5bps）とする（提示値ベース）。スリッページ 5bps は BT で再調整。

## 3. システム構成（論理）

- `data_provider`: ヒストリカル/リアルタイムの OHLCV 取得。キャッシュとレート制御を担当。
- `indicator_engine`: インジケータ計算（VWAP, BB, RSI, ADX, EMA, ATR）。計算窓と更新を統一。
- `strategy_core`: レジーム判定（15 分足）とエントリー/決済判定（1 分足）。状態遷移とパラメータ保持。
- `risk_manager`: 同時ポジション上限、クールダウン、連敗ストップ、日次損失制限。
- `broker_client`: Hyperliquid API ラッパ（約定/注文/残高/ポジション）。エラーハンドリングとリトライ。
- `backtester`: 過去データでの逐次シミュレーション。スリッページ/手数料モデルを注入可能。
- `runner`: 実行モード切替（backtest/live）、スケジューリング、ジョブ制御。
- `logger/metrics`: 構造化ログ（JSONLines）、メトリクス集計（P&L, 勝率, DD, レイテンシ）。
- `notifier`: Slack 通知（オープン/クローズ、理由、P&L、環境ラベル）。

## 4. データフロー（要約）

1. Runner がモードを決定（BT/Live）。
2. DataProvider が 1 分/15 分足を供給（BT 時は再生、Live 時は WS+REST）。
3. IndicatorEngine が最新バーでインジケータ更新。
4. StrategyCore がレジーム判定（15 分足確定ごと）→ Range ON/OFF 切替。
5. Range ON 中のみ 1 分足でエントリー/決済判定。RiskManager で制限チェック。
6. BrokerClient（BT 時はシミュレーション）へ注文要求 → 結果を状態に反映。
7. Logger/Metrics が記録し、Notifier が Slack へ送信。

## 5. モジュール設計（I/F 概要）

- DataProvider
  - `get_ohlcv(symbol, timeframe, start, end)` ジェネレータ/イテレータ。
  - Live 用 WS 購読と REST フォールバックを抽象化。レート制限/再接続を内包。
- IndicatorEngine
  - 入力: 新バー、保持するローリングバッファ。
  - 出力: {vwap, bb_upper/lower/middle, rsi, adx, ema50/200, atr}。
  - 実装: pandas/numba 併用。計算窓長はパラメータ化。
- StrategyCore
  - `update(bar_1m, bar_15m=None)` → {signal, reason, target_levels}。
  - レジーム: ADX<20、BB 幅比率<0.5%、EMA50/200 平行・接近、VWAP 回帰性。
  - エントリー: VWAP 乖離（±0.5〜0.8%）、BB タッチ、RSI 閾値、反転足条件、クールダウン/連敗チェック。
  - 決済: VWAP/BB ミドル到達、TP/SL 幅、時間切れ（10〜15 分）。
- RiskManager
  - ステート: 連敗数、直近クローズ時刻、日次損失累積。
  - 判定: 同時ポジション=1、クールダウン、連敗ストップ、日次損失ストップ。
- BrokerClient (Hyperliquid)
  - `create_order(side, size, type, price=None, sl=None, tp=None)` / `close_position`.
  - 必要 API: 認証/署名方式、REST エンドポイント、WS 約定フィード、レート上限。
  - 失敗時: リトライ（指数バックオフ）、部分約定・キャンセルハンドリング。
- Backtester
  - 入力: ヒストリカル 1m/15m、手数料/スリッページモデル。
  - 出力: トレード一覧、メトリクス、ログ。
  - リプレイ: 15 分足を 1 分に同期し、確定タイミングでレジーム判定。
- Notifier
  - Slack Webhook/SDK。環境ラベル（bt/live）を付与。
  - 送信内容: シンボル、方向、数量、エントリー/クローズ価格、トリガー理由、実現 P&L、タイムスタンプ。

## 6. パラメータ/設定管理

- `config/strategy.yaml`: レジーム閾値、VWAP 乖離、RSI、BB 条件、TP/SL、時間切れ、ATR フィルタ、稼働時間帯。
- `config/risk.yaml`: 同時ポジション上限、クールダウン、連敗/日次損失しきい値。
- `config/env.yaml`: API エンドポイント、手数料率、スリッページモデル、Slack URL、環境種別。
- `.env`: 秘匿情報（API キー/シークレット、Slack トークン）。
- 変更は Git 管理し、バージョンタグとパラメータセットを紐付け（BT 結果との対応表を残す）。
- 初期パラメータ案（プロトレード寄り、BT で調整前提）:
  - レジーム: ADX<20、BB 幅/価格<0.5%、VWAP 回帰性、EMA50/200 並行性（角度/乖離は要実装指標）
  - エントリー: VWAP 乖離 ±0.6%、RSI ロング<25/ショート>75、BB タッチ＋反転足
  - TP/SL: TP +0.30%、SL -0.22%、時間切れ 12 分
  - リスク: 同時 1 ポジ、クールダウン 4 分、連敗ストップ 3 回、日次損失しきい値 -2%（任意 ON）
  - フィルタ: 急騰急落 ATR×2.5 で 5 分停止、低ボラ ATR 閾値は BT で調整

## 7. 非機能・運用

- 信頼性: API 失敗時のリトライ＋サーキットブレーカ。WS 切断時の REST フォールバック。
- パフォーマンス: 1 分足処理は<1 秒目標。インジ計算はローリング更新で軽量化。
- 観測性: 構造化ログ（INFO:シグナル、WARN:スキップ理由、ERROR:API 失敗）。メトリクス（勝率、PF、DD、平均保持時間、レイテンシ）。
- デプロイ: Docker 化を前提。将来クラウドでは Secrets Manager/Parameter Store で鍵管理。デモ環境を挟まず、BT→ 本番移行のためロールバック手段（緊急停止/手動フラグ）を用意。

## 8. テスト方針

- Unit: Indicator 計算、判定ロジック（レンジ ON/OFF、エントリー/決済条件）、RiskManager。
- Integration: StrategyCore + Backtester でダミー価格系列を用いたシグナル検証。
- E2E(BT): 実データリプレイで勝率/PF/DD が算出されること。
- Live 最小ロット検証: 本番環境で極小ロット発注 → 即キャンセルし、約定/通知/ログを確認（デモ口座を挟まず BT 後に本番移行する前提の安全確認）。
- シミュレーション設定: 手数料とスリッページをパラメータで注入（固定 bps/価格%）。

## 9. Hyperliquid API 利用で必要になる資料とタイミング

- 実装前に必要: 認証方式（署名/nonce）、REST/WS エンドポイント URL、レートリミット、取引ペア仕様（ティックサイズ、ロット刻み）、手数料体系。
- 発注実装時に必要: 注文作成/キャンセル API 仕様、レスポンスフォーマット、エラーコード、部分約定/強制決済イベント。
- ライブ運用前に必要: 約定/ポジション更新用 WS チャネル仕様、メンテナンス時の挙動、ヘルスチェック方法。
  → 上記が揃ったタイミングで `broker_client` と `data_provider` を詳細設計/実装（BT 完了後すぐ本番移行する前提）。

## 10. AI 実装支援に関する考慮

- コード生成時に守るべき I/F と契約を上記に明文化し、テストケースを先に用意（AI 出力の品質担保）。
- パラメータ/設定ファイルのスキーマを事前に固定し、型チェック（pydantic 等）で検証。
- 自動生成コードに対し、必須ログ/例外メッセージのフォーマットを指定してレビュー容易化。
- 署名は公式 Python SDK の `sign_user_signed_action` など既存実装を利用し、自前実装は避ける。リクエスト生成は自前でも良いが署名部分だけ SDK ラッパ経由に統一する。

## 11. Hyperliquid 連携メモ

- REST/WS エンドポイントと主要 API 仕様は `docs/hyperliquid/` に整理済み（exchange/info/websocket/nonce/エラー/レート/署名等）。
- 署名は Python SDK 利用前提（パッケージ: `hyperliquid-python-sdk`、インストール時のバージョンを固定）。リクエスト生成は自前でもよいが署名だけ SDK ラッパ経由に統一。
- API ウォレット（agent）/サブアカウント運用方針は `hyperliquid_nonces_and_api_wallets.md` を参照（マスター鍵は使用せず agent 鍵を利用）。
- BTC パーペチュアルの `meta` 取得済み: assetIndex=0, szDecimals=5, maxLeverage=40, marginTableId=56（2025-05-時点）。設定にハードコード可。

## 12. 今後の ToDo（設計詳細化のフック）

- Hyperliquid API 仕様の取り込みと `broker_client` I/F 固定。
- バックテスト用データ取得経路の選定（入手先、フォーマット、保管場所）。
- パラメータ初期値の決定（要件の目安値を config に反映）。
- Slack 通知フォーマットと環境ラベルの決定。
- デプロイ目標環境（クラウド）の暫定選定と Secrets 管理方式の確定。

## 13. ドキュメント構成

- 基本設計サマリ: `docs/basic_design.md`（本書）
- 詳細設計ドラフト: `docs/design/` 配下に各モジュール（broker_client, data_provider, runner, strategy_core, indicator_engine, risk_manager, backtester, notifier, logging_metrics, config_schema, test_plan）
- Hyperliquid API 整理: `docs/hyperliquid/`（exchange/info/websocket/nonce/error/signing/rate_limits 等）

## 14. 実装ディレクトリ構成（初期案）

```
src/
  core/                   # 戦略ドメイン（純粋ロジック）
    strategy_core.py
    indicator_engine.py
    risk_manager.py
  infra/                  # 外部I/O層（差し替えやすくする）
    data_provider/        # WS/REST・ヒストリカル取得
    broker_client/        # Hyperliquid REST/WS
    notifier/             # Slack送信
    logging_metrics/      # 構造化ログ/メトリクス
  runner/                 # DIとモード切替（bt/live）
  backtester/             # リプレイ・約定モデル
  config/                 # 設定読み込み・バリデーション
  utils/                  # 共通ユーティリティ（時刻・リトライ等）
tests/
  unit/
  integration/
  fixtures/
config/
  strategy.yaml
  risk.yaml
  env.yaml
  env.example            # 秘匿除外のサンプル
scripts/
  fetch_ohlcv.py         # ヒストリカル取得→Parquet
  run_backtest.py
  run_live.py
data/
  ohlcv_1m.parquet
  ohlcv_15m.parquet
requirements.txt         # 依存（または pyproject.toml）
Makefile                 # lint/test/fmt/bt エイリアス
README.md                # セットアップと主要コマンド
```

運用方針:
- core/ は外部依存を持たず、infra 層の I/F を注入してテスト容易性を確保する。
- infra/ は外部I/O境界をまとめ、モック差し替えやすくする（BT/Live切替用）。
- runner は config 読み込み→依存解決→モード起動の単一エントリとする。
- tests は unit/integration を分け、fixtures にダミーデータ・モックレスポンスを置く。
