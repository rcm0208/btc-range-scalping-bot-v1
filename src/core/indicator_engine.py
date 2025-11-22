from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict, Iterable, List, Optional

from src.utils import Bar, Indicators, Timeframe


class UnsupportedTimeframeError(ValueError):
    """Raised when an unsupported timeframe is provided."""

    def __init__(self, timeframe: Timeframe):
        super().__init__(f"Unsupported timeframe: {timeframe}")


def _empty_indicators() -> Indicators:
    """Pylance/mypy 向けの初期値ヘルパー。"""
    return {
        "vwap": None,
        "bb_upper": None,
        "bb_middle": None,
        "bb_lower": None,
        "rsi": None,
        "adx": None,
        "ema50": None,
        "ema200": None,
        "atr": None,
    }


def _has_invalid_values(*values: float) -> bool:
    return any(not math.isfinite(v) for v in values)


@dataclass
class _RsiState:
    prev_close: Optional[float] = None
    avg_gain: Optional[float] = None
    avg_loss: Optional[float] = None
    init_gain_sum: float = 0.0
    init_loss_sum: float = 0.0
    init_count: int = 0


@dataclass
class _AdxState:
    prev_high: Optional[float] = None
    prev_low: Optional[float] = None
    prev_close: Optional[float] = None
    smoothed_tr: Optional[float] = None
    smoothed_dm_pos: Optional[float] = None
    smoothed_dm_neg: Optional[float] = None
    adx: Optional[float] = None
    tr_window: List[float] = field(default_factory=list)
    dm_pos_window: List[float] = field(default_factory=list)
    dm_neg_window: List[float] = field(default_factory=list)


@dataclass
class _AtrState:
    prev_close: Optional[float] = None
    atr: Optional[float] = None
    tr_window: List[float] = field(default_factory=list)


@dataclass
class _TimeframeState:
    vwap_num: float = 0.0
    vwap_den: float = 0.0
    bb_closes: Deque[float] = field(default_factory=deque)
    rsi: _RsiState = field(default_factory=_RsiState)
    adx: _AdxState = field(default_factory=_AdxState)
    atr: _AtrState = field(default_factory=_AtrState)
    ema_fast: Optional[float] = None
    ema_slow: Optional[float] = None
    latest: Indicators = field(default_factory=_empty_indicators)


class IndicatorEngine:
    """VWAP/BB/RSI/ADX/EMA/ATR をローリング更新するエンジン。"""

    def __init__(
        self,
        bb_period: int = 20,
        bb_std: float = 2.0,
        rsi_period: int = 7,
        adx_period: int = 14,
        ema_fast_period: int = 50,
        ema_slow_period: int = 200,
        atr_period: int = 20,
        supported_timeframes: set[Timeframe] | None = None,
    ) -> None:
        self.bb_period = bb_period
        self.bb_std = bb_std
        self.rsi_period = rsi_period
        self.adx_period = adx_period
        self.ema_fast_period = ema_fast_period
        self.ema_slow_period = ema_slow_period
        self.atr_period = atr_period
        self._states: Dict[Timeframe, _TimeframeState] = {}
        self._supported_timeframes: set[Timeframe] = supported_timeframes or {"1m", "15m"}

    def update(self, timeframe: Timeframe, bar: Bar) -> Indicators:
        state = self._get_state(timeframe)
        close = float(bar["close"])
        high = float(bar["high"])
        low = float(bar["low"])
        volume = float(bar["volume"])

        if _has_invalid_values(close, high, low, volume):
            # Skip update to avoid poisoning cumulative state
            return state.latest

        vwap = self._update_vwap(state, high, low, close, volume)
        bb_upper, bb_middle, bb_lower = self._update_bollinger(state, close)
        rsi = self._update_rsi(state, close)
        adx = self._update_adx(state, high, low, close)
        ema50 = self._update_ema(state, close, is_fast=True)
        ema200 = self._update_ema(state, close, is_fast=False)
        atr = self._update_atr(state, high, low, close)

        indicators: Indicators = {
            "vwap": vwap,
            "bb_upper": bb_upper,
            "bb_middle": bb_middle,
            "bb_lower": bb_lower,
            "rsi": rsi,
            "adx": adx,
            "ema50": ema50,
            "ema200": ema200,
            "atr": atr,
        }
        state.latest = indicators
        return indicators

    def get_latest(self, timeframe: Timeframe) -> Indicators:
        state = self._get_state(timeframe)
        return state.latest

    def warmup(self, timeframe: Timeframe, bars: Iterable[Bar]) -> None:
        for bar in bars:
            self.update(timeframe, bar)

    def _get_state(self, timeframe: Timeframe) -> _TimeframeState:
        if timeframe not in self._supported_timeframes:
            raise UnsupportedTimeframeError(timeframe)
        if timeframe not in self._states:
            self._states[timeframe] = _TimeframeState(
                bb_closes=deque(maxlen=self.bb_period)
            )
        return self._states[timeframe]

    def _update_vwap(
        self, state: _TimeframeState, high: float, low: float, close: float, volume: float
    ) -> Optional[float]:
        typical = (high + low + close) / 3.0
        state.vwap_num += typical * volume
        state.vwap_den += volume
        if state.vwap_den <= 0:
            return None
        return state.vwap_num / state.vwap_den

    def _update_bollinger(self, state: _TimeframeState, close: float) -> tuple[Optional[float], Optional[float], Optional[float]]:
        state.bb_closes.append(close)
        if len(state.bb_closes) < self.bb_period:
            return None, None, None
        mean = sum(state.bb_closes) / self.bb_period
        variance = sum((c - mean) ** 2 for c in state.bb_closes) / self.bb_period
        std = math.sqrt(variance)
        return (
            mean + self.bb_std * std,
            mean,
            mean - self.bb_std * std,
        )

    def _update_ema(self, state: _TimeframeState, close: float, is_fast: bool) -> float:
        period = self.ema_fast_period if is_fast else self.ema_slow_period
        current = state.ema_fast if is_fast else state.ema_slow
        if current is None:
            updated = close
        else:
            k = 2 / (period + 1)
            updated = close * k + current * (1 - k)
        if is_fast:
            state.ema_fast = updated
        else:
            state.ema_slow = updated
        return updated

    def _update_rsi(self, state: _TimeframeState, close: float) -> Optional[float]:
        rsi_state = state.rsi
        prev_close = rsi_state.prev_close
        rsi_state.prev_close = close
        if prev_close is None:
            return None

        delta = close - prev_close
        gain = delta if delta > 0 else 0.0
        loss = -delta if delta < 0 else 0.0

        if rsi_state.avg_gain is None or rsi_state.avg_loss is None:
            if rsi_state.init_count < self.rsi_period:
                rsi_state.init_count += 1
                rsi_state.init_gain_sum += gain
                rsi_state.init_loss_sum += loss
                if rsi_state.init_count == self.rsi_period:
                    rsi_state.avg_gain = rsi_state.init_gain_sum / self.rsi_period
                    rsi_state.avg_loss = rsi_state.init_loss_sum / self.rsi_period
            return None

        rsi_state.avg_gain = (
            (rsi_state.avg_gain * (self.rsi_period - 1)) + gain
        ) / self.rsi_period
        rsi_state.avg_loss = (
            (rsi_state.avg_loss * (self.rsi_period - 1)) + loss
        ) / self.rsi_period

        if rsi_state.avg_loss == 0:
            if rsi_state.avg_gain == 0:
                return 50.0
            return 100.0
        rs = rsi_state.avg_gain / rsi_state.avg_loss
        return 100 - (100 / (1 + rs))

    def _true_range(
        self,
        high: float,
        low: float,
        prev_close: Optional[float],
    ) -> float:
        if prev_close is None:
            return high - low
        return max(
            high - low,
            abs(high - prev_close),
            abs(low - prev_close),
        )

    def _update_adx(self, state: _TimeframeState, high: float, low: float, close: float) -> Optional[float]:
        adx_state = state.adx
        if adx_state.prev_high is None or adx_state.prev_low is None or adx_state.prev_close is None:
            adx_state.prev_high = high
            adx_state.prev_low = low
            adx_state.prev_close = close
            return None

        up_move = high - adx_state.prev_high
        down_move = adx_state.prev_low - low
        dm_pos = up_move if up_move > down_move and up_move > 0 else 0.0
        dm_neg = down_move if down_move > up_move and down_move > 0 else 0.0
        tr = self._true_range(high, low, adx_state.prev_close)

        adx_state.prev_high = high
        adx_state.prev_low = low
        adx_state.prev_close = close

        if adx_state.smoothed_tr is None:
            adx_state.tr_window.append(tr)
            adx_state.dm_pos_window.append(dm_pos)
            adx_state.dm_neg_window.append(dm_neg)
            if len(adx_state.tr_window) < self.adx_period:
                return None
            adx_state.smoothed_tr = sum(adx_state.tr_window)
            adx_state.smoothed_dm_pos = sum(adx_state.dm_pos_window)
            adx_state.smoothed_dm_neg = sum(adx_state.dm_neg_window)
            dx_values: list[float] = []
            smoothed_tr = adx_state.smoothed_tr
            smoothed_dm_pos = adx_state.smoothed_dm_pos
            smoothed_dm_neg = adx_state.smoothed_dm_neg
            for i in range(self.adx_period):
                if smoothed_tr == 0:
                    break
                di_pos_i = 100 * (smoothed_dm_pos / smoothed_tr)
                di_neg_i = 100 * (smoothed_dm_neg / smoothed_tr)
                dx_values.append(self._compute_dx(di_pos_i, di_neg_i))
            if dx_values:
                adx_state.adx = sum(dx_values) / len(dx_values)
            else:
                adx_state.adx = 0.0
            return adx_state.adx

        # Defensive check: normally initialized above, but guard for corrupted state
        if (
            adx_state.smoothed_tr is None
            or adx_state.smoothed_dm_pos is None
            or adx_state.smoothed_dm_neg is None
        ):
            return adx_state.adx

        adx_state.smoothed_tr = adx_state.smoothed_tr - (adx_state.smoothed_tr / self.adx_period) + tr
        adx_state.smoothed_dm_pos = adx_state.smoothed_dm_pos - (adx_state.smoothed_dm_pos / self.adx_period) + dm_pos
        adx_state.smoothed_dm_neg = adx_state.smoothed_dm_neg - (adx_state.smoothed_dm_neg / self.adx_period) + dm_neg

        if adx_state.smoothed_tr == 0:
            return adx_state.adx

        di_pos = 100 * (adx_state.smoothed_dm_pos / adx_state.smoothed_tr)
        di_neg = 100 * (adx_state.smoothed_dm_neg / adx_state.smoothed_tr)
        dx = self._compute_dx(di_pos, di_neg)

        if adx_state.adx is None:
            adx_state.adx = dx
        else:
            adx_state.adx = ((adx_state.adx * (self.adx_period - 1)) + dx) / self.adx_period
        return adx_state.adx

    @staticmethod
    def _compute_dx(di_pos: float, di_neg: float) -> float:
        denominator = di_pos + di_neg
        if denominator == 0:
            return 0.0
        return 100 * abs(di_pos - di_neg) / denominator

    def _update_atr(self, state: _TimeframeState, high: float, low: float, close: float) -> Optional[float]:
        atr_state = state.atr
        tr = self._true_range(high, low, atr_state.prev_close)
        atr_state.prev_close = close

        if atr_state.atr is None:
            atr_state.tr_window.append(tr)
            if len(atr_state.tr_window) < self.atr_period:
                return None
            atr_state.atr = sum(atr_state.tr_window) / self.atr_period
            return atr_state.atr

        atr_state.atr = (
            (atr_state.atr * (self.atr_period - 1)) + tr
        ) / self.atr_period
        return atr_state.atr
