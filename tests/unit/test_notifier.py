from __future__ import annotations

from unittest import mock

import httpx
import pytest

from src.infra.notifier import MissingWebhookError, Notifier


def test_missing_webhook_is_rejected() -> None:
    with pytest.raises(MissingWebhookError):
        Notifier("", "bt")


def test_notify_success_posts_payload() -> None:
    dummy_request = httpx.Request("POST", "https://example.com/hook")
    response = httpx.Response(200, request=dummy_request)
    with mock.patch.object(httpx.Client, "post", return_value=response) as mocked_post:
        notifier = Notifier("https://example.com/hook", "bt")
        notifier.notify({"event": "test", "message": "ok"})

        mocked_post.assert_called_once()
        called_args, called_kwargs = mocked_post.call_args
        assert called_args[0] == "https://example.com/hook"
        # content is bytes; ensure envが付与される
        assert "\"env\": \"bt\"" in called_kwargs["content"]


def test_env_label_cannot_be_overridden() -> None:
    dummy_request = httpx.Request("POST", "https://example.com/hook")
    response = httpx.Response(200, request=dummy_request)
    with mock.patch.object(httpx.Client, "post", return_value=response) as mocked_post:
        notifier = Notifier("https://example.com/hook", "bt")
        notifier.notify({"event": "test", "env": "fake"})

        called_kwargs = mocked_post.call_args.kwargs
        assert "\"env\": \"bt\"" in called_kwargs["content"]


def test_notify_raises_on_http_error() -> None:
    dummy_request = httpx.Request("POST", "https://example.com/hook")
    error_response = httpx.Response(500, text="error", request=dummy_request)
    with mock.patch.object(httpx.Client, "post", return_value=error_response):
        notifier = Notifier("https://example.com/hook", "bt")
        with pytest.raises(httpx.HTTPStatusError):
            notifier.notify({"event": "test"})
