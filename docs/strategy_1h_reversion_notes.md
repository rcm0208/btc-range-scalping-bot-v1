# 1h リバーション簡易バックテスト (2023-01-01〜2025-11-24)

- コンフィグ: `config/strategy_1h.yaml`
  - TF: signal=1h, trend=null, require_trend=true (ADX/EMA バイアス必須)
  - regime: adx_min=14, ema_gap_pct_min=0.0005
  - entry: mode=reversion, bb_touch_buffer_pct=0.001, rsi_long_max=25, rsi_short_min=75, htf_vwap_pullback_pct=0.0, ema200_guard_pct=0.0005, atr_sl_mult=1.2, min_stop_pct=0.001, rr_ratio=1.1, timeout_minutes=240, session制限なし
- データ/環境: `data/ohlcv_1h.parquet`（Binance 1h 全期間を再取得し、2023-03-24 13:00〜14:00 の欠損を補完済み）、`config/env.yaml`, `config/risk.yaml`（cooldown=4m, max_consecutive_losses=3）
- 実行: `PYTHONPATH=. python scripts/run_backtest.py --strategy config/strategy_1h.yaml --start <start> --end <end> --output <path>`

## 成果サマリ（full=2023-01-01〜2025-11-24）
| 期間 | PF | Win率 | 取引数 | Total Return | Max DD |
| --- | --- | --- | --- | --- | --- |
| full | 1.99 | 62.5% | 8 | +2.02% | 1.53% |
| 2023 | inf | 100% | 3 | +2.93% | 0.00% |
| 2024 | 1.59 | 66.7% | 3 | +0.41% | 0.70% |
| 2025Q4 | 0.00 | 0.0% | 1 | -0.39% | 0.39% |

## メモ
- 取引数が少なく、特に 2025Q4 は 1 トレードのみで -0.39%（PF=0）。現状は全期間で PF≈2 だがサンプル不足のため過学習リスクあり。
- 1h データ欠損（2023-03-24 13:00〜14:00）は未補完のまま。必要なら `scripts/fetch_ohlcv.py` で再取得して埋めること。
- さらなる調整案: timeout/ATR/rr_ratio の再グリッド、セッション時間帯や pullback ガード追加で 2025Q4 の単発負けを抑制すること。***
