from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, TypedDict, cast

from src.utils import Bar, Indicators, OpenPosition, Side, Signal, SignalType


@dataclass
class RegimeParams:
    """レンジ判定に利用するパラメータセット。"""

    adx_max: float
    bb_width_pct_max: float
    ema_flatness_threshold: float
    ema_spread_pct_max: float
    vwap_reversion_check: bool = True
    vwap_deviation_pct_max: float | None = None  # None時はbb_width_pct_maxを使用


@dataclass
class RegimeEvaluation:
    """レジーム判定結果。"""

    is_range: bool
    reason: str
    context: Dict[str, float | None]


@dataclass
class EntryParams:
    """エントリー・決済判定に利用するパラメータセット。"""

    vwap_deviation_pct_long: float
    vwap_deviation_pct_short: float
    rsi_long_max: float
    rsi_short_min: float
    tp_pct: float
    sl_pct: float
    timeout_minutes: int
    pin_bar_ratio: float = 2.0  # ピンバーのヒゲ/実体比率


class _EntryEvaluation(TypedDict):
    """エントリー条件の評価結果（モジュール内部用）。"""

    vwap_dev: float
    rsi: float
    bb_touch: bool
    reversal: bool


class StrategyCore:
    """レンジ判定とシグナル生成を担うコア。"""

    def __init__(self, regime_params: RegimeParams, entry_params: EntryParams) -> None:
        self.regime_params = regime_params
        self.entry_params = entry_params
        self.regime_on: bool = False
        self._prev_ema50: Optional[float] = None
        self._prev_ema200: Optional[float] = None

    def update(
        self,
        bar_1m: Bar,
        indicators_1m: Indicators,
        bar_15m: Optional[Bar] = None,
        indicators_15m: Optional[Indicators] = None,
        open_position: Optional[OpenPosition] = None,
    ) -> Signal:
        """1分足のシグナル判定を行う。15分足が渡された場合はレジームを更新する。"""
        if bar_15m is not None and indicators_15m is not None:
            self.update_regime(bar_15m, indicators_15m)

        exit_signal = self._maybe_exit(bar_1m, open_position)
        if exit_signal:
            return exit_signal
        if open_position is not None:
            return self._make_signal(
                "hold",
                open_position["side"],
                "position_open_hold",
                open_position["tp_level"],
                open_position["sl_level"],
                open_position["timeout_ms"],
                {"regime_on": self.regime_on},
            )

        if not self.regime_on:
            return self._make_signal(
                signal_type="skip",
                side=None,
                reason="regime_off",
                tp_level=None,
                sl_level=None,
                timeout_ms=None,
                context={"regime_on": False},
            )

        return self._maybe_enter(bar_1m, indicators_1m)

    def update_regime(self, bar_15m: Bar, indicators_15m: Indicators) -> RegimeEvaluation:
        """15分足確定時のレジーム判定を行い、Range ON/OFF を状態として保持する。"""
        close = float(bar_15m["close"])
        adx = indicators_15m.get("adx")
        bb_upper = indicators_15m.get("bb_upper")
        bb_lower = indicators_15m.get("bb_lower")
        ema50 = indicators_15m.get("ema50")
        ema200 = indicators_15m.get("ema200")
        vwap = indicators_15m.get("vwap")

        context: Dict[str, float | None] = {
            "adx": adx,
            "bb_width_pct": None,
            "ema_spread_pct": None,
            "ema50_slope_pct": None,
            "ema200_slope_pct": None,
            "vwap_deviation_pct": None,
        }

        if any(
            value is None
            for value in (
                adx,
                bb_upper,
                bb_lower,
                ema50,
                ema200,
                vwap,
            )
        ):
            evaluation = RegimeEvaluation(
                is_range=False,
                reason="indicators_warming_up",
                context=context,
            )
            self._seed_ema_state(ema50, ema200)
            self.regime_on = False
            return evaluation

        adx_f = cast(float, adx)
        bb_upper_f = cast(float, bb_upper)
        bb_lower_f = cast(float, bb_lower)
        ema50_f = cast(float, ema50)
        ema200_f = cast(float, ema200)
        vwap_f = cast(float, vwap)

        bb_width_pct = self._compute_pct(bb_upper_f - bb_lower_f, close)
        ema_spread_pct = self._compute_pct(abs(ema50_f - ema200_f), close)
        ema50_slope_pct = self._compute_slope_pct(self._prev_ema50, ema50_f, close)
        ema200_slope_pct = self._compute_slope_pct(self._prev_ema200, ema200_f, close)
        vwap_deviation_pct = self._compute_pct(abs(close - vwap_f), close)

        context.update(
            {
                "bb_width_pct": bb_width_pct,
                "ema_spread_pct": ema_spread_pct,
                "ema50_slope_pct": ema50_slope_pct,
                "ema200_slope_pct": ema200_slope_pct,
                "vwap_deviation_pct": vwap_deviation_pct,
            }
        )

        params = self.regime_params
        flat_ready = ema50_slope_pct is not None and ema200_slope_pct is not None
        flat_reason = "ema_slope_uninitialized" if not flat_ready else "ema_not_flat"

        flat_enough = False
        if flat_ready:
            ema50_slope_val = cast(float, ema50_slope_pct)
            ema200_slope_val = cast(float, ema200_slope_pct)
            flat_enough = (
                ema50_slope_val <= params.ema_flatness_threshold
                and ema200_slope_val <= params.ema_flatness_threshold
            )
        else:
            flat_enough = False

        # ADX閾値: <= を使用（設計書の「ADX < 20」に対し、境界値20をレンジ扱い）
        conditions = [
            (adx_f <= params.adx_max, "adx_above_threshold"),
            (
                bb_width_pct is not None and bb_width_pct <= params.bb_width_pct_max,
                "bb_width_too_wide",
            ),
            (
                ema_spread_pct is not None and ema_spread_pct <= params.ema_spread_pct_max,
                "ema_spread_too_wide",
            ),
            (flat_enough, flat_reason),
        ]

        if params.vwap_reversion_check:
            # VWAP乖離の閾値: vwap_deviation_pct_maxが未設定の場合はbb_width_pct_maxを使用
            effective_vwap_max = (
                params.vwap_deviation_pct_max
                if params.vwap_deviation_pct_max is not None
                else params.bb_width_pct_max
            )
            conditions.append(
                (
                    vwap_deviation_pct is not None
                    and vwap_deviation_pct <= effective_vwap_max,
                    "vwap_not_reverting",
                )
            )

        is_range = all(flag for flag, _ in conditions)
        reason = "range_on" if is_range else next(reason for flag, reason in conditions if not flag)

        evaluation = RegimeEvaluation(
            is_range=is_range,
            reason=reason,
            context=context,
        )
        self.regime_on = is_range
        self._seed_ema_state(ema50, ema200)
        return evaluation

    def _maybe_exit(self, bar_1m: Bar, open_position: Optional[OpenPosition]) -> Optional[Signal]:
        if open_position is None:
            return None

        side = open_position["side"]
        tp = open_position["tp_level"]
        sl = open_position["sl_level"]
        timeout_ms = open_position["timeout_ms"]
        now_ms = int(bar_1m["end_ms"])
        elapsed = now_ms - open_position["entry_time_ms"]

        high = float(bar_1m["high"])
        low = float(bar_1m["low"])

        if side == "long":
            if low <= sl:
                return self._make_signal(
                    "exit",
                    side,
                    "stop_loss",
                    tp,
                    sl,
                    timeout_ms,
                    {"hit": "sl", "price": low},
                )
            if high >= tp:
                return self._make_signal(
                    "exit",
                    side,
                    "take_profit",
                    tp,
                    sl,
                    timeout_ms,
                    {"hit": "tp", "price": high},
                )
        else:
            if high >= sl:
                return self._make_signal(
                    "exit",
                    side,
                    "stop_loss",
                    tp,
                    sl,
                    timeout_ms,
                    {"hit": "sl", "price": high},
                )
            if low <= tp:
                return self._make_signal(
                    "exit",
                    side,
                    "take_profit",
                    tp,
                    sl,
                    timeout_ms,
                    {"hit": "tp", "price": low},
                )

        if elapsed >= timeout_ms:
            return self._make_signal("exit", side, "timeout", tp, sl, timeout_ms, {"elapsed_ms": elapsed})

        return None

    def _maybe_enter(self, bar_1m: Bar, indicators_1m: Indicators) -> Signal:
        close = float(bar_1m["close"])
        open_ = float(bar_1m["open"])
        high = float(bar_1m["high"])
        low = float(bar_1m["low"])
        bb_upper = indicators_1m.get("bb_upper")
        bb_lower = indicators_1m.get("bb_lower")
        vwap = indicators_1m.get("vwap")
        rsi = indicators_1m.get("rsi")

        if any(value is None for value in (bb_upper, bb_lower, vwap, rsi)):
            return self._make_signal(
                "hold",
                None,
                "indicators_missing",
                None,
                None,
                None,
                {"bb_upper": bb_upper, "bb_lower": bb_lower, "vwap": vwap, "rsi": rsi},
            )

        params = self.entry_params
        sl_pct_abs = abs(params.sl_pct)

        bb_lower_f = cast(float, bb_lower)
        bb_upper_f = cast(float, bb_upper)
        vwap_f = cast(float, vwap)
        rsi_f = cast(float, rsi)

        long_candidate = self._evaluate_long(
            close=close,
            open_=open_,
            low=low,
            bb_lower=bb_lower_f,
            vwap=vwap_f,
            rsi=rsi_f,
            params=params,
        )
        if long_candidate:
            tp_level = close * (1 + params.tp_pct)
            sl_level = close * (1 - sl_pct_abs)
            return self._make_signal(
                "enter",
                "long",
                "enter_long",
                tp_level,
                sl_level,
                params.timeout_minutes * 60_000,
                {**long_candidate},
            )

        short_candidate = self._evaluate_short(
            close=close,
            open_=open_,
            high=high,
            bb_upper=bb_upper_f,
            vwap=vwap_f,
            rsi=rsi_f,
            params=params,
        )
        if short_candidate:
            tp_level = close * (1 - params.tp_pct)
            sl_level = close * (1 + sl_pct_abs)
            return self._make_signal(
                "enter",
                "short",
                "enter_short",
                tp_level,
                sl_level,
                params.timeout_minutes * 60_000,
                {**short_candidate},
            )

        return self._make_signal(
            "hold",
            None,
            "no_entry_conditions_met",
            None,
            None,
            None,
            {
                "close": close,
                "rsi": rsi,
                "bb_upper": bb_upper,
                "bb_lower": bb_lower,
                "vwap": vwap,
            },
        )

    def _evaluate_long(
        self,
        *,
        close: float,
        open_: float,
        low: float,
        bb_lower: float,
        vwap: float,
        rsi: float,
        params: EntryParams,
    ) -> Optional[_EntryEvaluation]:
        bb_touch = close <= bb_lower
        vwap_dev = self._vwap_deviation_pct(vwap, close, bias="below")
        reversal = self._bullish_reversal(open_, close, low, bb_lower)
        if (
            bb_touch
            and vwap_dev is not None
            and vwap_dev >= params.vwap_deviation_pct_long
            and rsi <= params.rsi_long_max
            and reversal
        ):
            return {
                "vwap_dev": vwap_dev,
                "rsi": rsi,
                "bb_touch": True,
                "reversal": True,
            }
        return None

    def _evaluate_short(
        self,
        *,
        close: float,
        open_: float,
        high: float,
        bb_upper: float,
        vwap: float,
        rsi: float,
        params: EntryParams,
    ) -> Optional[_EntryEvaluation]:
        bb_touch = close >= bb_upper
        vwap_dev = self._vwap_deviation_pct(vwap, close, bias="above")
        reversal = self._bearish_reversal(open_, close, high, bb_upper)
        if (
            bb_touch
            and vwap_dev is not None
            and vwap_dev >= params.vwap_deviation_pct_short
            and rsi >= params.rsi_short_min
            and reversal
        ):
            return {
                "vwap_dev": vwap_dev,
                "rsi": rsi,
                "bb_touch": True,
                "reversal": True,
            }
        return None

    def _bullish_reversal(self, open_: float, close: float, low: float, bb_lower: float) -> bool:
        """
        強気反転パターンの判定。
        - outside_in: バンド外で始まりバンド境界で終値（close >= bb_lower かつ open_ <= bb_lower）
        - pin_bar: 下ヒゲが実体のpin_bar_ratio倍以上
        注: outside_in条件とbb_touch条件の組み合わせにより、実質的にclose == bb_lowerのケースが該当
        """
        body = abs(close - open_)
        lower_wick = min(open_, close) - low
        outside_in = open_ <= bb_lower and close >= bb_lower
        ratio = self.entry_params.pin_bar_ratio
        pin_bar = lower_wick >= body * ratio if body > 0 else lower_wick > 0
        return outside_in or pin_bar

    def _bearish_reversal(self, open_: float, close: float, high: float, bb_upper: float) -> bool:
        """
        弱気反転パターンの判定。
        - outside_in: バンド外で始まりバンド境界で終値（close <= bb_upper かつ open_ >= bb_upper）
        - pin_bar: 上ヒゲが実体のpin_bar_ratio倍以上
        注: outside_in条件とbb_touch条件の組み合わせにより、実質的にclose == bb_upperのケースが該当
        """
        body = abs(close - open_)
        upper_wick = high - max(open_, close)
        outside_in = open_ >= bb_upper and close <= bb_upper
        ratio = self.entry_params.pin_bar_ratio
        pin_bar = upper_wick >= body * ratio if body > 0 else upper_wick > 0
        return outside_in or pin_bar

    def _vwap_deviation_pct(self, vwap: float, price: float, bias: str) -> Optional[float]:
        if vwap <= 0:
            return None
        if bias == "below":
            return (vwap - price) / vwap if vwap > price else 0.0
        return (price - vwap) / vwap if price > vwap else 0.0

    def _make_signal(
        self,
        signal_type: SignalType,
        side: Optional[Side],
        reason: str,
        tp_level: Optional[float],
        sl_level: Optional[float],
        timeout_ms: Optional[int],
        context: Optional[Dict[str, object]],
    ) -> Signal:
        return {
            "type": signal_type,
            "side": side,
            "reason": reason,
            "tp_level": tp_level,
            "sl_level": sl_level,
            "timeout_ms": timeout_ms,
            "context": context,
        }

    def _compute_pct(self, numerator: float, denominator: float) -> Optional[float]:
        if denominator <= 0:
            return None
        return numerator / denominator

    def _compute_slope_pct(
        self,
        previous: Optional[float],
        current: Optional[float],
        price: float,
    ) -> Optional[float]:
        if previous is None or current is None:
            return None
        return self._compute_pct(abs(current - previous), price)

    def _seed_ema_state(self, ema50: Optional[float], ema200: Optional[float]) -> None:
        if ema50 is not None:
            self._prev_ema50 = ema50
        if ema200 is not None:
            self._prev_ema200 = ema200


__all__ = ["EntryParams", "RegimeEvaluation", "RegimeParams", "StrategyCore"]
