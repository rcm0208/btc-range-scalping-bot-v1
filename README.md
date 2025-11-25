BTC Range Scalping Bot v1（概要）
================================

プロト段階の開発メモです。すべて日本語で記載しています。

## セットアップ
- 前提: Python 3.11+
- 仮想環境（推奨）: `python -m venv .venv && source .venv/bin/activate`
- 依存インストール: `pip install -r requirements.txt`  
  （依存が増えたら requirements.txt / pyproject.toml を更新）

## コンフィグ
- 戦略・リスク・環境設定: `config/strategy.yaml`, `config/risk.yaml`, `config/env.yaml`
- 機密値: `config/env.example` を参考に `.env` を作成して管理（Hyperliquid agent鍵・Slack Webhookなど）

## ドキュメントの読み順
1. `docs/requirements.md`（要件のソースオブトゥルース）
2. `docs/basic_design.md`（基本設計・ディレクトリ構成）
3. `docs/design/` 配下の詳細設計
4. `docs/hyperliquid/`（取引所仕様・署名・レートリミット）

## ディレクトリ概要
- `src/` 本体コード（core: 戦略/指標/リスク、infra: I/O、runner/backtester/config/utils）
- `tests/` ユニット・インテグレーション・fixtures
- `config/` 戦略・リスク・環境設定
- `scripts/` ユーティリティ（バックテスト/ライブ実行ラッパ想定）
- `data/` ローカルバックテスト用データ（git 管理外推奨）

## よく使うコマンド（今後 Makefile/pyproject でエイリアス化予定）
- フォーマット: `black .`
- Lint: `ruff check .`
- テスト: `pytest -q`

## バックテスト実行（暫定）
- 事前準備
  - `config/env.yaml` の `data_paths.ohlcv_1m` / `ohlcv_15m` に手元の Parquet を設定（例: `data/ohlcv_1m.parquet`）
  - 手数料/スリッページは `env.yaml` の `taker_fee_pct` と `slippage_model.value` を参照
- 実行例
  ```
  python scripts/run_backtest.py \
    --start 2024-01-01T00:00:00Z \
    --end   2024-01-02T00:00:00Z \
    --env config/env.yaml \
    --strategy config/strategy.yaml \
    --risk config/risk.yaml \
    --output backtest_result.json \
    --position-size 1.0 \
    --base-equity 1.0
  ```
- 出力: `backtest_result.json` にトレード一覧と summary（win_rate, profit_factor, max_drawdown など）。PyYAML が無い環境では設定を JSON 形式で記述しても動作可。
