# config スキーマ（ドラフト）

ここに strategy.yaml / risk.yaml / env.yaml / .env のキーと型・必須項目を記載する。

## 提案スキーマ（初期値は basic_design.md を参照）

### strategy.yaml
- symbol: string (e.g., "BTCUSDT")
- candle_intervals:
  - signal: string ("1m" | "15m" | "1h" | "4h")
  - trend: string | null (省略/Nullで signal と同一足を使用)
- regime:
  - adx_min: float
  - ema_gap_pct_min: float  # ema50/ema200 乖離の下限
  - require_trend: bool     # バイアスが取れないときにスキップするか
- entry:
  - mode: string ("reversion" | "breakout")
  - bb_touch_buffer_pct: float
  - rsi_long_max: float
  - rsi_short_min: float
  - htf_vwap_pullback_pct: float
  - ema200_guard_pct: float
  - atr_sl_mult: float
  - min_stop_pct: float
  - rr_ratio: float
  - timeout_minutes: int
  - session_start_hour_utc: int | null
  - session_end_hour_utc: int | null

### risk.yaml
- max_open_positions: int (1)
- cooldown_minutes: int (4)
- max_consecutive_losses: int (3)
- daily_loss_limit_pct: float (optional, e.g., -0.02)
- use_daily_loss_limit: bool

### env.yaml
- api_base: string (default "https://api.hyperliquid.xyz")
- ws_base: string (default "wss://api.hyperliquid.xyz/ws")
- taker_fee_pct: float (e.g., 0.00045)  # 0.045% = 4.5bps
- maker_fee_pct: float (e.g., 0.00015)  # 0.015% = 1.5bps
- slippage_model: { type: "bps", value: 0.0005 } # 初期案: 5bps（BTで再調整）
- slack_webhook_url: string
- environment: string ("bt" | "live")
- data_paths:
  - ohlcv_1m: string (e.g., "data/ohlcv_1m.parquet")
  - ohlcv_15m: string (e.g., "data/ohlcv_15m.parquet")
  - ohlcv_1h: string (optional)
  - ohlcv_4h: string (optional)

### .env（秘匿）
- HL_AGENT_PRIVATE_KEY
- HL_API_BASE (override)
- HL_WS_BASE (override)
- SLACK_WEBHOOK_URL (override)
- EXTRA: ログ/メトリクス外部送信先があれば適宜

## バリデーション方針（案）
- 価格/率系は実数で0以上（slippage/fee）、閾値は0〜1未満に制限。
- RSI閾値は0〜100の範囲。
- VWAP乖離は正の値のみ（符号はlong/shortで使い分け）。
- timeout_minutes, cooldown_minutes は正の整数。
- daily_loss_limit_pct は負の値を許容し、use_daily_loss_limit=trueのとき必須。
- data_paths は存在確認（読み書き許可）を起動時に検証。

## デフォルト値（初期案）
- strategy: signal=4h, trend=null, regime(adx_min=12, ema_gap_pct_min=0.0006), entry(mode=reversion, bb_touch_buffer_pct=0.0005, rsi_long_max=35, rsi_short_min=65, atr_sl_mult=1.8, rr_ratio=2.0, timeout_minutes=720)
- risk: max_open_positions=1, cooldown_minutes=4, max_consecutive_losses=3, daily_loss_limit_pct=-0.02, use_daily_loss_limit=false
- env: taker_fee_pct=0.00045, maker_fee_pct=0.00015, slippage_model(bps=0.0005), environment="bt" or "live"
