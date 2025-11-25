# 4h BB リバーション戦略 v1（実装中ロジックの記録）

## 概要
- 足: signal=4h, trend=None（同一足でバイアス判定）
- トレンド判定: ADX + EMA50/EMA200 乖離下限で方向バイアスを決定
- エントリー: ボリンジャーバンド下/上タッチ付近＋RSI閾値＋EMA200ガード、HTF VWAP 要求なし
- 決済: 固定RRのTP/SL、タイムアウト
- タイムウィンドウ: セッション制限なし

## パラメータ（config/strategy.yaml 現行）
- Regime
  - `adx_min`: 10
  - `ema_gap_pct_min`: 0.0005
  - `require_trend`: true
- Entry
  - `mode`: reversion
  - `bb_touch_buffer_pct`: 0.001
  - `rsi_long_max`: 30
  - `rsi_short_min`: 64
  - `htf_vwap_pullback_pct`: 0.0
  - `ema200_guard_pct`: 0.0005
  - `atr_sl_mult`: 1.8
  - `min_stop_pct`: 0.001
  - `rr_ratio`: 1.8
  - `timeout_minutes`: 720
  - `session_start_hour_utc` / `session_end_hour_utc`: null

## 成績メモ（パラメータ更新後）
- 2023-01-01〜2024-01-01（OOS）: PF 1.45 / 勝率 50% / +1.50% / トレード8 / DD 3.30%
- 2024-01-01〜2025-01-01（準インサンプル）: PF 1.47 / 勝率 70% / +2.23% / トレード10 / DD 2.35%
- 2025-09-01〜2025-11-24（OOS）: PF 1.82 / +2.43% / トレード4 / DD 2.95%
- 2023-01-01〜2025-11-24（全体）: PF 2.20 / 勝率 65.4% / +12.29% / トレード26 / DD 3.30%

## 課題
- 2023 年でPFが落ち、リターンがマイナス。全期間でロバストにするための追加チューニングが必要。
