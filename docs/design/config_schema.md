# config スキーマ（ドラフト）

ここに strategy.yaml / risk.yaml / env.yaml / .env のキーと型・必須項目を記載する。

## 提案スキーマ（初期値は basic_design.md を参照）

### strategy.yaml
- symbol: string (e.g., "BTC")
- vwap_deviation_pct_long: float (e.g., 0.006)  # 0.6%（符号は判定ロジック側で付与）
- vwap_deviation_pct_short: float (e.g., 0.006)  # 0.6%（符号は判定ロジック側で付与）
- rsi_long_max: float (e.g., 25)
- rsi_short_min: float (e.g., 75)
- tp_pct: float (e.g., 0.003)  # +0.30%
- sl_pct: float (e.g., -0.0022) # -0.22%
- timeout_minutes: int (e.g., 12)
- pin_bar_ratio: float (e.g., 2.0)  # ピンバーのヒゲ/実体比率
- atr_spike_multiplier: float (e.g., 2.5)
- atr_low_vol_threshold: float (optional, TBD via BT)
- regime:  # レンジ判定関連のまとめ
  - adx_max: float (e.g., 20)
  - bb_width_pct_max: float (e.g., 0.005) # 0.5%
  - ema_flatness_threshold: float (TBD)   # EMA50/200 の傾きしきい値
  - ema_spread_pct_max: float (e.g., 0.0015) # EMA50/200 乖離の上限（BTで調整）
  - vwap_reversion_check: bool (true)
  - vwap_deviation_pct_max: float (e.g., 0.005) # VWAP乖離の上限（未設定時はbb_width_pct_maxを使用）
- candle_intervals:
  - trend: "15m"
  - signal: "1m"
- schedule:
  - enabled: bool
  - windows: [ { start: "HH:MM", end: "HH:MM" }, ... ]

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
- strategy: vwap_deviation_pct=0.006, rsi_long_max=25, rsi_short_min=75, tp_pct=0.003, sl_pct=-0.0022, timeout=12分, adx_max=20, bb_width_pct_max=0.005
- risk: max_open_positions=1, cooldown_minutes=4, max_consecutive_losses=3, daily_loss_limit_pct=-0.02, use_daily_loss_limit=false
- env: taker_fee_pct=0.00045, maker_fee_pct=0.00015, slippage_model(bps=0.0005), environment="bt" or "live"
