# よく使うコマンド
- 初回セットアップ: `python -m venv .venv && source .venv/bin/activate && python -m pip install -U pip`
- 依存インストール: `pip install -r requirements.txt`（現状空。依存追加時に更新）
- フォーマット: `black .`
- Lint: `ruff check .`
- テスト: `pytest -q`
- ビルド/実行: runner/backtester/scrpits は未実装。将来 `python scripts/run_backtest.py` / `python scripts/run_live.py` などを想定。