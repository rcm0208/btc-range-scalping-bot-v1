from __future__ import annotations

import json
import logging
from typing import Any, Mapping

import backoff
import httpx

logger = logging.getLogger(__name__)


class MissingWebhookError(ValueError):
    """Webhook URL が未設定の場合の例外。"""

    def __init__(self) -> None:
        super().__init__("Slack webhook URL is required")


def _should_give_up(exc: Exception) -> bool:
    """バックオフを諦める条件(主に4xxクライアントエラー)。"""
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code < 500
    return False


class Notifier:
    """Slack Webhook 送信の簡易ラッパー。"""

    def __init__(self, webhook_url: str, environment: str, timeout: float = 5.0) -> None:
        if not webhook_url:
            raise MissingWebhookError()
        self.webhook_url = webhook_url
        self.environment = environment
        self.client = httpx.Client(timeout=timeout)

    def __enter__(self) -> "Notifier":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        self.close()

    def close(self) -> None:
        """Explicitly close the underlying HTTP client."""
        self.client.close()

    @backoff.on_exception(
        backoff.expo,
        httpx.HTTPError,
        max_tries=3,
        jitter=backoff.full_jitter,
        giveup=_should_give_up,
    )
    def notify(self, event: Mapping[str, Any]) -> None:
        """環境ラベルを付与してSlackへ送信する。"""
        payload = {**event, "env": self.environment}
        try:
            response = self.client.post(
                self.webhook_url,
                headers={"Content-Type": "application/json"},
                content=json.dumps(payload),
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            if isinstance(exc, httpx.HTTPStatusError):
                logger.warning(
                    "Slack notification failed (status=%s, body=%s)",
                    exc.response.status_code,
                    exc.response.text,
                )
            else:
                logger.warning("Slack notification failed with network error: %s", exc)
            raise


__all__ = ["MissingWebhookError", "Notifier"]
