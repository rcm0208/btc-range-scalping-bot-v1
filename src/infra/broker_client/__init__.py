from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, Mapping, Optional

import httpx


@dataclass
class AssetSpec:
    coin: str = "BTC"
    asset_index: int = 0
    sz_decimals: int = 5
    max_price_decimals: int = 6  # perpsは6
    tick_size: float = 0.1
    min_notional: float = 10.0  # MinTradeNtl

    def __post_init__(self) -> None:
        if self.sz_decimals < 0:
            raise ValueError("sz_decimals must be non-negative")
        if self.tick_size <= 0:
            raise ValueError("tick_size must be positive")
        if self.min_notional <= 0:
            raise ValueError("min_notional must be positive")


class BrokerClient:
    """Hyperliquid用 broker クライアントのスタブ。

    - httpx クライアント初期化のみ実装
    - SDK 署名呼び出し枠を用意
    - tick/lot/MinTradeNtl のバリデーション枠を用意
    """

    def __init__(
        self,
        api_base: str,
        private_key: str,
        *,
        asset_spec: AssetSpec | None = None,
        timeout: float = 10.0,
    ) -> None:
        if not private_key:
            raise ValueError("private_key is required")
        self.api_base = api_base
        self.private_key = private_key
        self.asset_spec = asset_spec or AssetSpec()
        self.client = httpx.Client(base_url=api_base, timeout=timeout)

    def prepare_order_payload(
        self,
        *,
        side: str,
        price: float,
        size: float,
        tif: str = "Gtc",
        reduce_only: bool = False,
        cloid: Optional[str] = None,
    ) -> Dict[str, Any]:
        """注文ペイロードを検証・整形する（送信は未実装）。"""
        is_buy = self._normalize_side(side)
        limit_px = self._validate_price(price)
        sz = self._validate_size(size)
        self._validate_notional(limit_px, sz)

        order: Dict[str, Any] = {
            "a": self.asset_spec.asset_index,
            "b": is_buy,
            "p": self._format_decimal(limit_px, self.asset_spec.max_price_decimals),
            "s": self._format_decimal(sz, self.asset_spec.sz_decimals),
            "r": reduce_only,
            "t": {"limit": {"tif": tif}},
        }
        if cloid:
            order["c"] = cloid

        payload: Dict[str, Any] = {
            "action": {
                "type": "order",
                "orders": [order],
                "grouping": "na",
            },
            "nonce": None,
        }
        return payload

    def sign_action(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        """SDK を用いた署名呼び出し枠。SDK 未導入時は ImportError。"""
        try:
            from hyperliquid.utils import sign_user_signed_action  # type: ignore
        except ImportError as exc:
            raise ImportError(
                "hyperliquid-python-sdk is required for signing; install and configure before live trading."
            ) from exc

        return sign_user_signed_action(self.private_key, payload)

    # --- validators ---
    def _normalize_side(self, side: str) -> bool:
        lowered = side.lower()
        if lowered not in {"buy", "sell"}:
            raise ValueError("side must be 'buy' or 'sell'")
        return lowered == "buy"

    def _validate_price(self, price: float) -> float:
        if price <= 0:
            raise ValueError("price must be positive")

        tick = Decimal(str(self.asset_spec.tick_size))
        px = Decimal(str(price))
        quantized_px = px.quantize(tick, rounding=ROUND_HALF_UP)
        tolerance = Decimal("1e-10")
        if abs(px - quantized_px) > tolerance:
            raise ValueError("price is not aligned to tick size")

        allowed_decimals = max(0, self.asset_spec.max_price_decimals)
        if self._count_decimals(quantized_px) > allowed_decimals:
            raise ValueError("price has too many decimal places for perp constraints")

        return float(quantized_px)

    def _validate_size(self, size: float) -> float:
        if size <= 0:
            raise ValueError("size must be positive")
        quant = Decimal(10) ** -self.asset_spec.sz_decimals
        sz_dec = Decimal(str(size)).quantize(quant, rounding=ROUND_HALF_UP)
        if abs(sz_dec - Decimal(str(size))) > Decimal("1e-12"):
            raise ValueError("size exceeds allowed precision for lot size")
        return float(sz_dec)

    def _validate_notional(self, price: Optional[float], size: float) -> None:
        if price is None:
            return
        notional = price * size
        if notional < self.asset_spec.min_notional:
            raise ValueError("order notional below minimum")

    def _format_decimal(self, value: float, decimals: int) -> str:
        quant = Decimal(10) ** -decimals
        quantized = Decimal(str(value)).quantize(quant, rounding=ROUND_HALF_UP).normalize()
        return format(quantized, "f")

    def _count_decimals(self, value: Decimal) -> int:
        # 非有限値や特殊値の場合は桁数検証をスキップ
        if not value.is_finite():
            return 0
        exponent = value.normalize().as_tuple().exponent
        if not isinstance(exponent, int):
            return 0
        return 0 if exponent >= 0 else -exponent


__all__ = ["AssetSpec", "BrokerClient"]
