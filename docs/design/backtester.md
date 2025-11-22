# backtester 設計（詳細）

## 役割
- ヒストリカル1m/15m OHLCVをリプレイし、indicator_engine/strategy_core/risk_manager/brokerシミュレーションを通じてP&Lを集計する。
- 手数料・スリッページモデルを注入し、メトリクスを算出。

## 入出力I/F（案）
- `run(params, data_provider, indicator_engine, strategy_core, risk_manager, fee_model, slippage_model) -> BacktestResult`
- `BacktestResult`: メトリクス、トレード一覧、エクイティカーブなど。

## リプレイ順序
1. 15m足の確定タイミングでレジーム判定。
2. 1m足を逐次処理、indicator_engineを更新→strategy_core.update→signalを取得。
3. risk_manager.can_enter を確認、許可なら疑似 broker で約定/キャンセルを処理。
4. 決済条件（TP/SL/時間切れ）は各1mバー終値を基準に判定（約定はOHLCレンジ内でスリッページ適用）。
5. on_close 時に risk_manager に通知。

## 約定モデル（初期案）
- 成行/指値: バーのOHLC範囲に到達したかで充足判定。単純化のためバー内どこかで成立したとみなす。
- スリッページ: bps固定（初期5bps）をエントリー・エグジット双方に適用（方向に応じて悪化）。
- 手数料: taker=0.045%、maker=0.015%（env.yaml初期値）を常に適用（BTでは成行扱いならtaker固定でも可。改善余地あり）。

## データ
- 入力: Parquetの1m/15m（data_provider経由で取得）。
- 欠損バー: スキップまたはNaN埋めをログ警告。基本は連続区間のみで集計。

## メトリクス出力
- 勝率、PF、最大DD、平均R/R、平均保持時間、手数料総額、スリッページ推定、日次/時間帯別PL。
- トレード一覧: entry_ts/px, exit_ts/px, side, pnl, fee, slip, reason(TP/SL/timeout)。
- エクイティカーブ: 時系列での累積PnL。

## パラメータ/シナリオ
- 複数パラメータセットを走らせ比較可能にする（スイープ機能は後回しでも可）。
- フィルタON/OFF（ATRスパイク、低ボラ、時間帯）でシナリオ分岐できるようにする。

## ログ/観測
- 各トレードの決済理由、スリッページ適用値、手数料をログ。
- エラーやデータ欠損は警告レベルで出力。

## TODO（実装時に確定）
- 約定モデルの詳細化（バー内の高値/安値でどの順序で当たるとみなすか）。
- maker/taker判定ロジックをBTで簡略化するか、すべてtakerとして計上するか。
- ウォームアップ期間の決定（インジケータが安定するまでのバーを除外）。
