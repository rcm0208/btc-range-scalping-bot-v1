# runner 設計（詳細）

## 役割
- モード切替（backtest / live）とジョブ制御、緊急停止フラグを管理。
- コンポーネントの初期化順序と依存解決を担う。

## モード
- `bt`: ヒストリカルデータをリプレイ（backtester呼び出し）
- `live`: WS購読でリアルタイム運用

## フラグ/制御
- 緊急停止フラグ: ファイル/フラグ/ENVなどでON時は新規エントリー禁止、必要ならポジションをクローズ（要ポリシー）。
- 環境ラベル: `env` = bt/live を全ログ・通知に付与。

## フロー（live）
1. config読込（env/strategy/risk）→ .env読み込み
2. data_provider起動（WS購読）→ indicator_engineウォームアップ
3. strategy_core + risk_manager インスタンス化
4. broker_client 初期化（署名キー読み込み）
5. メインループ: 1mバー到着ごとに strategy_core.update → risk_manager.can_enter → broker_client発注/キャンセル
6. orderUpdates/userEventsを購読して fills/約定を反映、risk_manager.on_close を呼ぶ
7. 緊急停止フラグ監視、エラー時リトライ/サーキットブレーカ

## フロー（bt）
1. config読込
2. data_provider からヒストリカルを供給
3. indicator_engineウォームアップ後、backtester.run を呼ぶ
4. 結果を保存（メトリクス、トレード一覧、エクイティカーブ）

## I/F（案）
- `run(mode: str, config_paths: ConfigPaths, flags: RunFlags) -> None`
- `RunFlags`: { emergency_stop_path?: str, dry_run?: bool }

## ログ/通知
- mode, env, 設定ファイルのハッシュ/バージョンをログ。
- 緊急停止発動時・致命的エラー時に Slack 通知。

## TODO（実装時）
- sync/asyncの統一（broker_clientとdata_providerに合わせる）。
- 緊急停止フラグの実装方法（ファイル監視 vs メモリフラグ vs シグナル）。
- backtest結果の保存形式（JSON/CSV/Parquet）を確定。
