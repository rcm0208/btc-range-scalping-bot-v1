# risk_manager 設計（詳細）

## 役割
- 戦略ロジックとは独立に取引制限を判定し、エントリー/クローズ可否を返す。
- ポジション状態、連敗数、日次損失などのステートを管理。

## 入出力I/F（案）
- `can_enter(now: datetime, side: str, pnl_stats: PnlStats) -> CheckResult`
- `on_close(now: datetime, pnl: float, is_win: bool) -> None`
- `reset_daily(now: datetime) -> None`（日次境界でリセット）
- 状態アクセサ: `current_state()` で連敗数、クールダウン残り、日次損失などを返す。

### CheckResult（例）
```
CheckResult = {
  "allowed": bool,
  "reason": Optional[str],  # 拒否時の理由（cooldown, losing_streak, daily_loss, already_open）
}
```

### PnlStats（例）
```
PnlStats = {
  "open_positions": int,
  "daily_realized_pct": float,   # 日次実現損益（%）
  "last_close_time": Optional[datetime],
  "losing_streak": int,
}
```

## 制限ロジック（初期案）
- 同時ポジション: 1 まで
- クールダウン: 最終クローズから X 分（初期4分）経過後までエントリー不可
- 連敗ストップ: 連続損切り 3 回で停止（次のリセットまたは手動解除まで）
- 日次損失制限: -2% 到達で停止（use_daily_loss_limit=true の場合）

## 状態管理
- `open_positions`（カウントのみ）
- `last_close_time`
- `losing_streak`（勝ちでリセット、負けで+1）
- `daily_realized_pct`（日付が変わったらリセット）
- 停止フラグ: `stopped_reason`（連敗 or 日次損失）を保持、解除は日次リセットまたは手動。

## イベントハンドリング
- `on_close` 呼び出し時に PnL を反映し、losing_streak/daily_realized_pct を更新。
- `reset_daily` は runner が日次境界で呼ぶ。必要なら手動解除APIも用意。

## ログ/通知
- 拒否理由をログに出力（cooldown, losing_streak, daily_loss, already_open）。
- 停止に達した場合は Slack 通知（連敗ストップ、日次損失ストップ）。

## TODO（実装時に確定）
- PnL計測の単位（% vs USD）をどちらで保持するか（現状%で想定）。
- 手動解除APIの有無（runnerからフラグ解除できるようにするか）。
- 部分クローズが入る場合の losing_streak 判定（損益基準を明示）。
