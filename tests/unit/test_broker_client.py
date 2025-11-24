from __future__ import annotations

import pytest

from src.infra.broker_client import AssetSpec, BrokerClient


def test_httpx_client_initializes_with_base_url() -> None:
    client = BrokerClient(api_base="https://api.example.com", private_key="0xabc")
    assert str(client.client.base_url) == "https://api.example.com"


def test_prepare_order_validates_tick_and_lot() -> None:
    spec = AssetSpec(tick_size=0.5, sz_decimals=5, min_notional=10.0)
    client = BrokerClient(api_base="https://api.example.com", private_key="0xabc", asset_spec=spec)

    payload = client.prepare_order_payload(side="buy", price=100.0, size=0.2)
    order = payload["action"]["orders"][0]

    assert order["b"] is True
    assert order["p"] == "100"
    assert order["s"] == "0.2"
    assert order["a"] == spec.asset_index
    assert "grouping" in payload["action"]


def test_prepare_order_rejects_off_tick_price() -> None:
    spec = AssetSpec(tick_size=0.5, sz_decimals=5)
    client = BrokerClient(api_base="https://api.example.com", private_key="0xabc", asset_spec=spec)

    with pytest.raises(ValueError):
        client.prepare_order_payload(side="sell", price=100.1, size=0.001)


def test_prepare_order_rejects_excess_precision() -> None:
    spec = AssetSpec(tick_size=0.1, sz_decimals=3)
    client = BrokerClient(api_base="https://api.example.com", private_key="0xabc", asset_spec=spec)

    with pytest.raises(ValueError):
        client.prepare_order_payload(side="buy", price=100.0, size=0.00012)


def test_price_decimals_independent_from_size_decimals() -> None:
    spec = AssetSpec(tick_size=0.0001, sz_decimals=5, max_price_decimals=4)
    client = BrokerClient(api_base="https://api.example.com", private_key="0xabc", asset_spec=spec)

    payload = client.prepare_order_payload(side="buy", price=123.4567, size=0.5)
    assert payload["action"]["orders"][0]["p"] == "123.4567"

    with pytest.raises(ValueError):
        client.prepare_order_payload(side="buy", price=123.45678, size=0.5)


def test_prepare_order_rejects_min_notional() -> None:
    spec = AssetSpec(tick_size=0.1, sz_decimals=5, min_notional=50.0)
    client = BrokerClient(api_base="https://api.example.com", private_key="0xabc", asset_spec=spec)

    with pytest.raises(ValueError):
        client.prepare_order_payload(side="buy", price=10.0, size=0.1)


def test_sign_action_requires_sdk() -> None:
    client = BrokerClient(api_base="https://api.example.com", private_key="0xabc")
    with pytest.raises(ImportError):
        client.sign_action({"type": "noop"})


def test_prepare_order_forbids_none_price() -> None:
    client = BrokerClient(api_base="https://api.example.com", private_key="0xabc")
    with pytest.raises(TypeError):
        client.prepare_order_payload(side="buy", price=None, size=1.0)  # type: ignore[arg-type]


def test_float_rounding_price_on_tick_passes() -> None:
    spec = AssetSpec(tick_size=0.1, sz_decimals=5, max_price_decimals=3, min_notional=0.1)
    client = BrokerClient(api_base="https://api.example.com", private_key="0xabc", asset_spec=spec)

    price = 0.1 + 0.2  # produces 0.30000000000000004 as float
    payload = client.prepare_order_payload(side="buy", price=price, size=1.0)

    assert payload["action"]["orders"][0]["p"] == "0.3"
