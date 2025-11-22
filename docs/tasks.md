# 開発タスクリスト

## 実装順の目安

1. config 雛形 / 型共有
2. indicator_engine
3. strategy_core
4. risk_manager
5. infra スタブ（data_provider → broker_client → notifier/logging）
6. backtester
7. runner
8. テスト/fixtures/ツール整備

番号は依存関係参照用に `[Txx]` を振っています。

## config・型共通

- [ ] [T01] config 雛形: `config/strategy.yaml` `risk.yaml` `env.yaml` `.env.example` を初期値で埋める。.env.example に必要キー（HL_AGENT_PRIVATE_KEY 等）を列挙し README に参照リンクを追記。参照: `docs/design/config_schema.md`, `docs/basic_design.md`。（依存なし）
- [ ] [T02] 型共有: `src/utils/types.py` に Bar 型・Indicators 型・Signal/CheckResult 等の共通型を定義し、core/infra から参照できるようにする。参照: `docs/design/strategy_core.md`, `docs/design/indicator_engine.md`。（依存: T01）

## indicator_engine

- [ ] [T10] ローリング更新: VWAP/BB/RSI/ADX/EMA/ATR を実装し、ウォームアップ長・NaN ガードを入れる。参照: `docs/design/indicator_engine.md`, `docs/basic_design.md`（指標一覧）。 （依存: T02）
- [ ] [T11] I/F 確定: `update(timeframe, bar)` / `get_latest(timeframe)` / `warmup` を実装し、簡易ユニットテスト 1 本を追加。（依存: T10）

## strategy_core

- [ ] [T20] レジーム判定: ADX/BB 幅/EMA 平行性・乖離/VWAP 回帰チェックで Range ON/OFF を状態保持する。参照: `docs/design/strategy_core.md`（レジーム）、`docs/requirements.md`。（依存: T11）
- [ ] [T21] シグナル生成: VWAP 乖離・BB タッチ・RSI・簡易反転足でエントリー、TP/SL/タイムアウトで決済。Signal 構造体を定義し、ON/OFF/エントリー各 1 ケースのユニットテストを追加。参照: `docs/design/strategy_core.md`（エントリー/決済）。 （依存: T20）

## risk_manager

- [ ] [T30] 制限実装: 同時ポジ=1、クールダウン、連敗ストップ、日次損失ストップ（オプション）を state 管理付きで実装。参照: `docs/design/risk_manager.md`, `docs/basic_design.md`（リスク）。 （依存: T02）
- [ ] [T31] 判定テスト: CheckResult/State 型を使い、許可/拒否/リセットのユニットテストを追加。（依存: T30）

## infra スタブ

- [ ] [T40] data_provider: Parquet 読み出しイテレータ雛形、WS 購読 I/F 定義、欠損バー警告ログ枠を用意。参照: `docs/design/data_provider.md`, `docs/hyperliquid/hyperliquid_websocket.md`。（依存: T02）
- [ ] [T41] broker_client: SDK 署名呼び出し枠、tick/lot/MinTradeNtl バリデーション枠、httpx クライアント初期化のみ。参照: `docs/design/broker_client.md`, `docs/hyperliquid/*`（tick/lot/署名/エラー/レート）。 （依存: T01）
- [ ] [T42] notifier: Slack webhook 送信関数（少回リトライ）、env ラベル付き payload を作成。参照: `docs/design/notifier.md`。（依存: T01）
- [ ] [T43] logging_metrics: JSON Lines ロガー初期化と標準キー固定、メトリクス集計の器だけ置く。参照: `docs/design/logging_metrics.md`。（依存: T01）

## backtester

- [ ] [T50] リプレイ実装: 1m/15m リプレイと約定モデル（OHLC 内 fill、固定 bps 手数料/スリッページ）を実装。参照: `docs/design/backtester.md`。（依存: T21, T31, T40）
- [ ] [T51] 集計: 勝率/PF/DD/平均保持時間のメトリクス集計と簡易サマリ出力を行う。（依存: T50）

## runner

- [ ] [T60] モード骨組み: bt/live モード切替、緊急停止フラグ読み込み、config 読込と依存生成のスタブを実装。参照: `docs/design/runner.md`, `docs/basic_design.md`（フロー）。 （依存: T01, T21, T31, T40, T41, T42, T43, T51）

## テスト/データ/ツール

- [ ] [T70] fixtures: 小さなダミー 1m/15m データを `tests/fixtures/` に配置し、backtester の smoke テストに流用。参照: `docs/design/data_provider.md`（Bar 形式）。 （依存: T02, T40）
- [ ] [T71] unit tests: indicator_engine / strategy_core / risk_manager 用に各 1 本追加。参照: 各 design ドキュメントのテスト方針。 （依存: T11, T21, T31）
- [ ] [T72] ツール整備: Makefile または pyproject で `black`, `ruff`, `pytest -q` エイリアスを用意し、README に記載。（依存なし）
