from __future__ import annotations

from unittest import mock
import json

import httpx
import pytest

from src.infra.notifier import MissingWebhookError, Notifier, _should_give_up


def test_missing_webhook_is_rejected() -> None:
    with pytest.raises(MissingWebhookError):
        Notifier("", "bt")


def test_notify_success_posts_payload() -> None:
    dummy_request = httpx.Request("POST", "https://example.com/hook")
    response = httpx.Response(200, request=dummy_request)
    with mock.patch.object(httpx.Client, "post", return_value=response) as mocked_post:
        notifier = Notifier("https://example.com/hook", "bt")
        notifier.notify({"event": "test", "message": "ok"})
        notifier.close()

        mocked_post.assert_called_once()
        called_args, called_kwargs = mocked_post.call_args
        assert called_args[0] == "https://example.com/hook"
        payload = json.loads(called_kwargs["content"])
        assert payload["env"] == "bt"
        assert payload["event"] == "test"
        assert payload["message"] == "ok"


def test_env_label_cannot_be_overridden() -> None:
    dummy_request = httpx.Request("POST", "https://example.com/hook")
    response = httpx.Response(200, request=dummy_request)
    with mock.patch.object(httpx.Client, "post", return_value=response) as mocked_post:
        notifier = Notifier("https://example.com/hook", "bt")
        notifier.notify({"event": "test", "env": "fake"})
        notifier.close()

        called_kwargs = mocked_post.call_args.kwargs
        assert "\"env\": \"bt\"" in called_kwargs["content"]


def test_notify_raises_on_http_error() -> None:
    dummy_request = httpx.Request("POST", "https://example.com/hook")
    error_response = httpx.Response(500, text="error", request=dummy_request)
    with mock.patch.object(httpx.Client, "post", return_value=error_response):
        notifier = Notifier("https://example.com/hook", "bt")
        with pytest.raises(httpx.HTTPStatusError):
            notifier.notify({"event": "test"})
        notifier.close()


def test_notify_gives_up_on_client_error() -> None:
    dummy_request = httpx.Request("POST", "https://example.com/hook")
    error_response = httpx.Response(400, text="bad", request=dummy_request)
    with mock.patch.object(httpx.Client, "post", return_value=error_response) as mocked_post:
        notifier = Notifier("https://example.com/hook", "bt")
        with pytest.raises(httpx.HTTPStatusError):
            notifier.notify({"event": "test"})
        notifier.close()
        assert mocked_post.call_count == 1  # 4xxはリトライしない


def test_should_give_up_allows_rate_limit_retry() -> None:
    dummy_request = httpx.Request("POST", "https://example.com/hook")
    rate_limited = httpx.Response(429, request=dummy_request)
    timeout_resp = httpx.Response(408, request=dummy_request)
    client_error = httpx.Response(400, request=dummy_request)

    for resp, expected in ((rate_limited, False), (timeout_resp, False), (client_error, True)):
        exc = httpx.HTTPStatusError("error", request=dummy_request, response=resp)
        assert _should_give_up(exc) is expected


def test_notifier_context_manager_closes_client() -> None:
    dummy_request = httpx.Request("POST", "https://example.com/hook")
    response = httpx.Response(200, request=dummy_request)
    with mock.patch.object(httpx.Client, "post", return_value=response), mock.patch.object(
        httpx.Client, "close"
    ) as mocked_close:
        with Notifier("https://example.com/hook", "bt") as notifier:
            notifier.notify({"event": "ctx"})
        mocked_close.assert_called_once()
