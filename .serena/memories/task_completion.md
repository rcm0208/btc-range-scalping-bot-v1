# タスク完了チェック
- 変更時は docs/requirements.md / docs/basic_design.md / docs/design/ の仕様差分があれば同時更新。
- コード変更後は `ruff check .`、`black .`、`pytest -q` を実行（利用環境準備が必要）。結果を PR/報告に記載。
- 新機能やロジック変更はユニットテストを追加（レンジ判定/エントリー/決済/リスク制御の境界・失敗ケースを含む）。
- Secrets は .env に置き、commmit しない。ログでマスクを確認。
- 実装に応じて config/ パラメータやサンプル (env.example) を更新し、使用方法を README に追記。
- 大きな変更は小さく分割し、コミットはコンベンショナルコミットに従う。