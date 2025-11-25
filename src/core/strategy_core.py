from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Optional

from src.utils import Bar, Indicators, OpenPosition, Side, Signal


@dataclass
class RegimeParams:
    """HTF トレンドバイアスの判定用パラメータ。"""

    adx_min: float = 18.0
    ema_gap_pct_min: float = 0.001  # ema50 と ema200 の乖離最小 (0.1%)
    require_trend: bool = True  # トレンド判定できなければ取引を見送る


@dataclass
class EntryParams:
    """1m BB リバーション＋HTF トレンドフィルターのパラメータ。"""

    mode: str = "reversion"  # "reversion" or "breakout"
    bb_touch_buffer_pct: float = 0.001  # バンドへのタッチ判定を緩和
    rsi_long_max: float = 38.0
    rsi_short_min: float = 62.0
    htf_vwap_pullback_pct: float = 0.002  # HTF VWAP からの押し/戻りを要求
    ema200_guard_pct: float = 0.001  # シグナル足の ema200 を大きく割らない/超えない
    atr_sl_mult: float = 1.6
    min_stop_pct: float = 0.0012  # ATR が極端に小さいときの下限
    rr_ratio: float = 1.8
    timeout_minutes: int = 90
    vwap_dev_pct_min: float = 0.0  # VWAP からの最小乖離（0で無効）
    atr_vol_min_pct: float = 0.0  # ATR/close の最小割合（低ボラのみ許可、0で無効）
    use_reversal_filter: bool = False  # 直近の推移が反転しつつあるかをチェック
    reversal_lookback: int = 3  # 反転判定に使う足数（現在足を含まない過去の足）
    use_wick_filter: bool = False  # ピンバー形状フィルタ
    wick_body_ratio_min: float = 1.5  # |wick|/body の下限
    wick_direction: str = "both"  # "both" / "long" / "short"
    cooldown_minutes_after_spike: int = 0  # 急変動後のクールダウン（0で無効）
    use_fib_filter: bool = False
    fib_retrace_min: float = 0.382
    fib_retrace_max: float = 0.618
    fib_lookback_bars: int = 50
    use_adx_range_filter: bool = False  # ADXが閾値未満のときのみ逆張りを許可
    adx_range_max: float = 20.0  # レンジ判定の最大ADX
    use_mid_tp: bool = False  # TPをBBミドルに設定
    session_start_hour_utc: Optional[int] = None
    session_end_hour_utc: Optional[int] = None


class StrategyCore:
    """15m トレンドに沿った 1m BB 押し目・戻り目リバーション戦略。"""

    def __init__(self, regime_params: RegimeParams, entry_params: EntryParams) -> None:
        self.regime_params = regime_params
        self.entry_params = entry_params
        self._recent_highs: list[float] = []
        self._recent_lows: list[float] = []
        self._recent_bars: list[Bar] = []
        self._spike_end_ms: Optional[int] = None

    def update(
        self,
        bar_signal: Bar,
        indicators_signal: Indicators,
        bar_trend: Optional[Bar] = None,
        indicators_trend: Optional[Indicators] = None,
        open_position: Optional[OpenPosition] = None,
    ) -> Signal:
        exit_signal = self._maybe_exit(bar_signal, open_position)
        if exit_signal:
            return exit_signal

        if open_position is not None:
            return self._hold(open_position)

        if not self._session_ok(int(bar_signal["end_ms"])):
            return self._skip("session_closed", {"hour": self._hour_utc(int(bar_signal["end_ms"]))})

        regime_ind = indicators_trend or indicators_signal
        bias = self._trend_bias(regime_ind, bar_trend or bar_signal)
        if bias is None and self.regime_params.require_trend:
            return self._skip("no_trend_bias", {"adx": regime_ind.get("adx") if regime_ind else None})

        return self._maybe_enter(bar_signal, indicators_signal, indicators_trend, bias)

    def _trend_bias(self, ind: Optional[Indicators], bar: Optional[Bar]) -> Optional[Side]:
        if not ind or bar is None:
            return None
        adx = ind.get("adx")
        ema_fast = ind.get("ema50")
        ema_slow = ind.get("ema200")
        if adx is None or ema_fast is None or ema_slow is None:
            return None
        adx_f = float(adx)
        close = float(bar["close"])
        gap_pct = abs(float(ema_fast) - float(ema_slow)) / close if close else 0.0
        if adx_f < self.regime_params.adx_min or gap_pct < self.regime_params.ema_gap_pct_min:
            return None
        if float(ema_fast) > float(ema_slow):
            return "long"
        if float(ema_fast) < float(ema_slow):
            return "short"
        return None

    def _maybe_enter(
        self,
        bar: Bar,
        ind_signal: Indicators,
        ind_trend: Optional[Indicators],
        bias: Optional[Side],
    ) -> Signal:
        self._record_bar(bar)
        close = float(bar["close"])
        high = float(bar["high"])
        low = float(bar["low"])
        rsi = ind_signal.get("rsi")
        bb_upper = ind_signal.get("bb_upper")
        bb_lower = ind_signal.get("bb_lower")
        ema_fast = ind_signal.get("ema50")
        ema_slow = ind_signal.get("ema200")
        atr = ind_signal.get("atr")
        vwap_signal = ind_signal.get("vwap")
        vwap_trend = ind_trend.get("vwap") if ind_trend else None

        if any(v is None for v in (rsi, bb_upper, bb_lower, ema_fast, ema_slow, atr, vwap_signal)):
            return self._skip(
                "indicators_missing",
                {
                    "rsi": rsi,
                    "bb_upper": bb_upper,
                    "bb_lower": bb_lower,
                    "ema50": ema_fast,
                    "ema200": ema_slow,
                    "atr": atr,
                    "vwap": vwap_signal,
                },
            )

        rsi_f = float(rsi)
        ema50 = float(ema_fast)
        ema200 = float(ema_slow)
        atr_f = float(atr)

        guard_long = close >= ema200 * (1 - self.entry_params.ema200_guard_pct)
        guard_short = close <= ema200 * (1 + self.entry_params.ema200_guard_pct)

        touch_lower = close <= float(bb_lower) * (1 + self.entry_params.bb_touch_buffer_pct)
        touch_upper = close >= float(bb_upper) * (1 - self.entry_params.bb_touch_buffer_pct)

        htf_pullback_ok_long = True
        htf_pullback_ok_short = True
        if vwap_trend is not None:
            htf_pullback_ok_long = close <= float(vwap_trend) * (1 - self.entry_params.htf_vwap_pullback_pct)
            htf_pullback_ok_short = close >= float(vwap_trend) * (1 + self.entry_params.htf_vwap_pullback_pct)

        mode = (self.entry_params.mode or "reversion").lower()
        if mode not in {"reversion", "breakout"}:
            mode = "reversion"

        vwap_dev_min = max(float(self.entry_params.vwap_dev_pct_min or 0.0), 0.0)
        vwap_dev_long_ok = True
        vwap_dev_short_ok = True
        if vwap_signal is not None and vwap_dev_min > 0:
            vwap_f = float(vwap_signal)
            vwap_dev_long_ok = close <= vwap_f * (1 - vwap_dev_min)
            vwap_dev_short_ok = close >= vwap_f * (1 + vwap_dev_min)

        atr_vol_min = max(float(self.entry_params.atr_vol_min_pct or 0.0), 0.0)
        if atr_vol_min > 0 and close > 0:
            if atr_f / close < atr_vol_min:
                return self._hold(None, reason="atr_vol_too_low", context={"atr_vol": atr_f / close})

        if self.entry_params.use_adx_range_filter:
            adx_val = ind_signal.get("adx")
            if adx_val is not None and float(adx_val) > self.entry_params.adx_range_max:
                return self._hold(None, reason="adx_too_high_for_range", context={"adx": float(adx_val)})

        def _update_spike_state() -> None:
            spike_mult = 3.0
            true_range = high - low
            if atr_f > 0 and true_range >= atr_f * spike_mult:
                self._spike_end_ms = int(bar["end_ms"])

        def _cooldown_ok() -> bool:
            minutes = max(int(self.entry_params.cooldown_minutes_after_spike or 0), 0)
            if minutes <= 0:
                return True
            if not self._spike_end_ms:
                return True
            end_ms = int(bar["end_ms"])
            return end_ms - self._spike_end_ms >= minutes * 60_000

        def _wick_ok(side: Side) -> bool:
            if not self.entry_params.use_wick_filter:
                return True
            body = abs(close - float(bar["open"]))
            if body == 0:
                return False
            upper = float(bar["high"]) - max(close, float(bar["open"]))
            lower = min(close, float(bar["open"])) - float(bar["low"])
            ratio_up = upper / body
            ratio_lo = lower / body
            need_ratio = self.entry_params.wick_body_ratio_min
            direction = (self.entry_params.wick_direction or "both").lower()
            if side == "long":
                if direction in {"both", "long"}:
                    return ratio_lo >= need_ratio
                if direction == "short":
                    return ratio_up >= need_ratio
            else:
                if direction in {"both", "short"}:
                    return ratio_up >= need_ratio
                if direction == "long":
                    return ratio_lo >= need_ratio
            return False

        def _reversal_ok(side: Side) -> bool:
            if not self.entry_params.use_reversal_filter:
                return True
            lookback = max(int(self.entry_params.reversal_lookback or 0), 0)
            bars = self._recent_bars[:-1] if self._recent_bars else []
            if len(bars) < lookback or lookback < 2:
                return False
            recent = bars[-lookback:]
            highs = [float(b["high"]) for b in recent]
            lows = [float(b["low"]) for b in recent]
            prev_close = float(recent[-1]["close"])
            if side == "long":
                descending_highs = all(h1 > h2 for h1, h2 in zip(highs, highs[1:]))
                descending_lows = all(l1 > l2 for l1, l2 in zip(lows, lows[1:]))
                return descending_highs and descending_lows and close > prev_close
            else:
                ascending_highs = all(h1 < h2 for h1, h2 in zip(highs, highs[1:]))
                ascending_lows = all(l1 < l2 for l1, l2 in zip(lows, lows[1:]))
                return ascending_highs and ascending_lows and close < prev_close

        def _wick_ok(side: Side) -> bool:
            if not self.entry_params.use_wick_filter:
                return True
            body = abs(close - float(bar["open"]))
            if body == 0:
                return False
            upper = float(bar["high"]) - max(close, float(bar["open"]))
            lower = min(close, float(bar["open"])) - float(bar["low"])
            ratio_up = upper / body
            ratio_lo = lower / body
            need_ratio = self.entry_params.wick_body_ratio_min
            direction = (self.entry_params.wick_direction or "both").lower()
            if side == "long":
                if direction in {"both", "long"}:
                    return ratio_lo >= need_ratio
                if direction == "short":
                    return ratio_up >= need_ratio
            else:
                if direction in {"both", "short"}:
                    return ratio_up >= need_ratio
                if direction == "long":
                    return ratio_lo >= need_ratio
            return False

        def _update_spike_state() -> None:
            spike_mult = 3.0
            true_range = high - low
            if atr_f > 0 and true_range >= atr_f * spike_mult:
                self._spike_end_ms = int(bar["end_ms"])

        def _cooldown_ok() -> bool:
            minutes = max(int(self.entry_params.cooldown_minutes_after_spike or 0), 0)
            if minutes <= 0:
                return True
            if not self._spike_end_ms:
                return True
            end_ms = int(bar["end_ms"])
            return end_ms - self._spike_end_ms >= minutes * 60_000

        _update_spike_state()

        if mode == "reversion":
            long_ready = (
                bias == "long"
                and touch_lower
                and rsi_f <= self.entry_params.rsi_long_max
                and guard_long
                and htf_pullback_ok_long
                and vwap_dev_long_ok
            )
            short_ready = (
                bias == "short"
                and touch_upper
                and rsi_f >= self.entry_params.rsi_short_min
                and guard_short
                and htf_pullback_ok_short
                and vwap_dev_short_ok
            )
        else:  # breakout along the trend
            long_ready = (
                bias == "long"
                and touch_upper
                and rsi_f >= self.entry_params.rsi_short_min
                and close >= ema50
                and guard_long
                and vwap_dev_short_ok
            )
            short_ready = (
                bias == "short"
                and touch_lower
                and rsi_f <= self.entry_params.rsi_long_max
                and close <= ema50
                and guard_short
                and vwap_dev_long_ok
            )

        sl_dist = max(atr_f * self.entry_params.atr_sl_mult, close * self.entry_params.min_stop_pct, (high - low) * 0.25)

        def _fib_ok(side: Side) -> bool:
            if not self.entry_params.use_fib_filter:
                return True
            if not self._recent_highs or not self._recent_lows:
                return False
            range_high = max(self._recent_highs)
            range_low = min(self._recent_lows)
            span = range_high - range_low
            if span <= 0:
                return False
            if side == "long":
                retrace = (range_high - close) / span
            else:
                retrace = (close - range_low) / span
            return self.entry_params.fib_retrace_min <= retrace <= self.entry_params.fib_retrace_max

        if long_ready:
            if not _fib_ok("long"):
                return self._hold(None, reason="fib_filter_block_long", context={"close": close})
            if not _reversal_ok("long"):
                return self._hold(None, reason="reversal_filter_block_long", context={"close": close})
            if not _wick_ok("long"):
                return self._hold(None, reason="wick_filter_block_long", context={"close": close})
            if not _cooldown_ok():
                return self._hold(None, reason="cooldown_spike", context={"close": close})
            sl = close - sl_dist
            tp = close + sl_dist * self.entry_params.rr_ratio
            if self.entry_params.use_mid_tp and bb_upper is not None and bb_lower is not None:
                tp = (float(bb_upper) + float(bb_lower)) / 2
            return self._enter(
                "long",
                tp,
                sl,
                {
                    "rsi": rsi_f,
                    "vwap_trend": vwap_trend,
                    "ema_gap": (ema50 - ema200) / close,
                },
            )

        if short_ready:
            if not _fib_ok("short"):
                return self._hold(None, reason="fib_filter_block_short", context={"close": close})
            if not _reversal_ok("short"):
                return self._hold(None, reason="reversal_filter_block_short", context={"close": close})
            if not _wick_ok("short"):
                return self._hold(None, reason="wick_filter_block_short", context={"close": close})
            if not _cooldown_ok():
                return self._hold(None, reason="cooldown_spike", context={"close": close})
            sl = close + sl_dist
            tp = close - sl_dist * self.entry_params.rr_ratio
            if self.entry_params.use_mid_tp and bb_upper is not None and bb_lower is not None:
                tp = (float(bb_upper) + float(bb_lower)) / 2
            return self._enter(
                "short",
                tp,
                sl,
                {
                    "rsi": rsi_f,
                    "vwap_trend": vwap_trend,
                    "ema_gap": (ema200 - ema50) / close,
                },
            )

        reason = "no_entry_conditions_met"
        return self._hold(None, reason=reason, context={"bias": bias, "touch_lower": touch_lower, "touch_upper": touch_upper})

    def _maybe_exit(self, bar: Bar, open_position: Optional[OpenPosition]) -> Optional[Signal]:
        if open_position is None:
            return None
        side = open_position["side"]
        tp = open_position["tp_level"]
        sl = open_position["sl_level"]
        timeout_ms = open_position["timeout_ms"]
        now_ms = int(bar["end_ms"])
        elapsed = now_ms - open_position["entry_time_ms"]
        high = float(bar["high"])
        low = float(bar["low"])

        if side == "long":
            if low <= sl:
                return self._exit(side, "stop_loss", tp, sl, timeout_ms, {"price": low})
            if high >= tp:
                return self._exit(side, "take_profit", tp, sl, timeout_ms, {"price": high})
        else:
            if high >= sl:
                return self._exit(side, "stop_loss", tp, sl, timeout_ms, {"price": high})
            if low <= tp:
                return self._exit(side, "take_profit", tp, sl, timeout_ms, {"price": low})

        if elapsed >= timeout_ms:
            return self._exit(side, "timeout", tp, sl, timeout_ms, {"elapsed_ms": elapsed})
        return None

    def _enter(self, side: Side, tp: float, sl: float, context: Dict[str, object]) -> Signal:
        return {
            "type": "enter",
            "side": side,
            "reason": f"enter_{side}",
            "tp_level": tp,
            "sl_level": sl,
            "timeout_ms": self.entry_params.timeout_minutes * 60_000,
            "tp1_level": None,
            "trailing_start": None,
            "context": context,
        }

    def _exit(self, side: Side, reason: str, tp: float, sl: float, timeout_ms: int, context: Dict[str, object]) -> Signal:
        return {
            "type": "exit",
            "side": side,
            "reason": reason,
            "tp_level": tp,
            "sl_level": sl,
            "timeout_ms": timeout_ms,
            "tp1_level": None,
            "trailing_start": None,
            "context": context,
        }

    def _hold(self, open_position: Optional[OpenPosition], reason: str = "hold", context: Optional[Dict[str, object]] = None) -> Signal:
        return {
            "type": "hold",
            "side": open_position["side"] if open_position else None,
            "reason": reason,
            "tp_level": open_position["tp_level"] if open_position else None,
            "sl_level": open_position["sl_level"] if open_position else None,
            "timeout_ms": open_position["timeout_ms"] if open_position else None,
            "tp1_level": open_position.get("tp1_level") if open_position else None,
            "trailing_start": open_position.get("trailing_start") if open_position else None,
            "context": context,
        }

    def _skip(self, reason: str, context: Optional[Dict[str, object]]) -> Signal:
        return {
            "type": "skip",
            "side": None,
            "reason": reason,
            "tp_level": None,
            "sl_level": None,
            "timeout_ms": None,
            "tp1_level": None,
            "trailing_start": None,
            "context": context,
        }

    def _session_ok(self, end_ms: int) -> bool:
        start = self.entry_params.session_start_hour_utc
        end = self.entry_params.session_end_hour_utc
        if start is None or end is None:
            return True
        hour = self._hour_utc(end_ms)
        if start < end:
            return start <= hour < end
        return hour >= start or hour < end

    @staticmethod
    def _hour_utc(end_ms: int) -> int:
        return datetime.fromtimestamp(end_ms / 1000, tz=timezone.utc).hour

    def _record_bar(self, bar: Bar) -> None:
        """維持中のレンジを簡易に記録（Fib・反転フィルタ用）。"""
        try:
            hi = float(bar["high"])
            lo = float(bar["low"])
        except Exception:
            return
        self._recent_highs.append(hi)
        self._recent_lows.append(lo)
        max_len = max(int(self.entry_params.fib_lookback_bars or 0), 0)
        if max_len:
            self._recent_highs = self._recent_highs[-max_len:]
            self._recent_lows = self._recent_lows[-max_len:]
        self._recent_bars.append(bar)
        bars_max = max(int(self.entry_params.reversal_lookback or 0) + 2, 10)
        self._recent_bars = self._recent_bars[-bars_max:]


__all__ = ["EntryParams", "RegimeParams", "StrategyCore"]
