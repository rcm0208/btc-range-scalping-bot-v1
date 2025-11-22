# Design Docs

このディレクトリは各モジュールの詳細設計を置く場所です。全体のドキュメント/コード構成の決定版は `docs/basic_design.md`（13. ドキュメント構成）を参照してください。本 README は入口案内のみとし、構成ツリーは重複管理しません。

対象ファイル（詳細設計の雛形／保守対象）:

- broker_client.md
- data_provider.md
- runner.md
- strategy_core.md
- indicator_engine.md
- risk_manager.md
- backtester.md
- notifier.md
- logging_metrics.md
- config_schema.md
- test_plan.md

運用ルール（推奨）:

- 追加・改廃があれば、先に `docs/basic_design.md` を更新してから本ディレクトリ配下を修正する。
- WIP は章冒頭に `Status: WIP` を明記し、完了したら削除する。
- インタフェース変更は必ず入力/出力/前提条件/例外をセットで記述する。
