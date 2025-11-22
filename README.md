BTC Range Scalping Bot v1
========================

開発メモ（プロト段階）

## セットアップ
- Python 3.11+ を前提。必要なら仮想環境を作成:
  - `python -m venv .venv && source .venv/bin/activate`
- 依存インストール（未定義の場合は後続で requirements.txt / pyproject.toml を整備）:
  - `pip install -r requirements.txt`

## コンフィグ
- 環境・戦略パラメータは `config/strategy.yaml` `config/risk.yaml` `config/env.yaml` を編集。
- 機密値は `config/env.example` を参考に `.env` を作成して管理する（Hyperliquid の agent 鍵や Slack Webhook など）。

## ドキュメントの読み順
1. `docs/requirements.md`（要件のソース）
2. `docs/basic_design.md`（基本設計・ディレクトリ構成）
3. `docs/design/` 配下のモジュール別詳細
4. `docs/hyperliquid/`（取引所仕様）

## ディレクトリ概要（実装）
- `src/` アプリ本体（core: 戦略ロジック、infra: 外部I/O、runner/backtester/config/utils）
- `tests/` ユニット/インテグレーション/fixtures
- `config/` 戦略・リスク・環境設定（env.example をベースに .env を用意）
- `scripts/` ユーティリティ（ヒストリカル取得・BT/LIVE 実行ラッパ）
- `data/` ローカルBT用データ（git 管理外推奨）

## 想定コマンド（今後整備）
- フォーマット: `black .`
- Lint: `ruff check .`
- テスト: `pytest -q`
Makefile/pyproject でエイリアスを後続追加予定。
