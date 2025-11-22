# strategy_core 設計（詳細）

## 役割
- 15m足でレンジ判定（Range ON/OFF）を行い、Range ON中のみ1m足でエントリー/決済シグナルを生成。
- リスク制限（連敗/クールダウン/日次損失）は risk_manager に委譲し、戦略ロジックに専念。

## 入出力I/F（案）
- `update(bar_1m: Bar, bar_15m: Optional[Bar]) -> Signal | None`
  - bar_15m は15分足確定時のみ渡す（15分確定ごとにレジーム再評価）。
  - 戻り値: Signal（enter/exit or hold）、理由・ターゲット水準付き。

### Signal構造（例）
```
Signal = {
  "type": "enter" | "exit" | "hold" | "skip",
  "side": "long" | "short" | None,
  "reason": str,              # 条件合致の説明
  "tp_level": Optional[float],
  "sl_level": Optional[float],
  "timeout_ms": Optional[int],
  "context": {...}            # デバッグ/ログ用
}
```

## レジーム判定（15m足）
- 条件（すべて満たす）:
  - ADX(14) < adx_max (初期20)
  - ボリンジャーバンド幅/価格 < bb_width_pct_max (初期0.5%)
  - EMA50/EMA200 が概ね平行・接近（傾きしきい値と乖離しきい値を後述）
  - 価格が15m VWAPの上下を行き来（乖離しきい値内）
- 判定タイミング: 15m足確定ごとに評価し、Range ON/OFFを状態として保持。
- EMA平行性・乖離の指標（案）:
  - 傾き: 直近N本のEMA差分の絶対値が threshold 以下
  - 乖離: |EMA50 - EMA200| / price < ema_spread_pct_max (初期案: 0.1%〜0.2%をBTで調整)

## エントリー判定（Range ON時の1m足）
- 共通前提: risk_manager の判定を通過し、同時ポジション=1前提。
- ロング条件:
  - 位置: 1m終値がBB下限タッチ/下抜け
  - VWAP乖離: price <= vwap * (1 - vwap_dev_long)（初期0.6%）
  - RSI(7) < rsi_long_max（初期25）
  - ローソク反転: ピンバー/包み足（バンド外→内で終値陽線）
- ショート条件: 上下反転（VWAP乖離 +0.6%、RSI>75、BB上限タッチ/上抜け、陰線戻り）
- Signal生成: enter {side, tp_level, sl_level, timeout_ms, reason}

## 決済ロジック
- TP: VWAP付近またはBBミドル付近。値幅目安: +0.30%
- SL: 値幅目安: -0.22%（エントリー直近高安を参照してずらす）
- 時間切れ: 12分（パラメータ）
- Range OFF時: 新規エントリー禁止。既存ポジションの強制決済はしない（別途ルールに応じて検討可）。

## 状態管理
- `regime` フラグ（ON/OFF）、最終評価時刻。
- 直近バー・インジケータを保持するバッファ参照は indicator_engine に委譲し、値は引数の bar に付属させるか、更新済みの構造体として渡す設計とする。
- ステートフル情報（ポジション有無、最後のエントリー時刻など）は上位（runner）または risk_manager が管理し、strategy_core は純粋ロジックを維持。

## パラメータ（初期案: basic_design に準拠）
- vwap_deviation_pct_long = 0.006, short = 0.006
- rsi_long_max = 25, rsi_short_min = 75
- tp_pct = 0.003, sl_pct = -0.0022
- timeout_minutes = 12
- adx_max = 20, bb_width_pct_max = 0.005
- ema_spread_pct_max = 0.001〜0.002（要BT調整）
- atr_spike_multiplier = 2.5（フィルタ用途）

## ログ/デバッグ
- 出力: reason, 条件判定の各閾値、使用した指標値（vwap, bb上下, rsi, adx, ema差, vwap乖離など）。
- スキップ理由（Range OFF、フィルタ、cooldown、連敗ストップ）は明示。

## TODO（決定/実装時）
- EMA平行性の定義確定（傾き計算期間と閾値）。
- 反転足の判定ロジック（ピンバーのヒゲ/実体比、包み足条件）。
- VWAP乖離の計算（15m VWAPを1m足にプロットする方法は indicator_engine 側で定義）。
- シグナルの出力形態（純粋関数 vs オブジェクトメソッド）とテストのしやすさを考慮したAPI。
