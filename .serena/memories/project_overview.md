# プロジェクト概要
- 目的: Hyperliquid 本番で BTCUSDT のレンジ相場に限定した VWAP 回帰型逆張りスキャルピング Bot。
- 設計ソース: docs/requirements.md（要件）、docs/basic_design.md（基本設計・モジュール構成）、docs/design/ 配下（詳細設計）、docs/hyperliquid/（API 仕様）。
- 技術スタック: Python 3.11+（PEP8/型ヒント必須、black/ruff/pytest 想定）。依存は requirements.txt（現状空）。
- ディレクトリ: src/（core=戦略・指標・リスク、infra=data_provider/broker_client/notifier/logging_metrics、runner/backtester/config/utils）、tests/（unit/integration/fixtures）、config/（env/strategy/risk yaml 想定、.env 管理）、scripts/（fetch/run_backtest/run_live 予定）、data/（BT 用データ）。
- 戦略要点: 15m でレンジ判定（ADX<20、BB 幅比率<0.5%、EMA50/200 横ばい接近、VWAP 回帰）、レンジ ON 時のみ 1m で BB タッチ＋VWAP 乖離±0.5〜0.8%、RSI 反転等で逆張り。TP VWAP/BB ミドル、SL -0.2〜-0.25% 目安、時間切れ 10〜15m、リスク（同時1ポジ、クールダウン、連敗/日次損失制限）。
- 未整備: requirements.txt/Makefile 空、実装は __init__.py 等のみでロジック未実装。