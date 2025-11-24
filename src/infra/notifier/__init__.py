from __future__ import annotations

import json
import logging
from typing import Any, Mapping, Optional

import backoff
import httpx

logger = logging.getLogger(__name__)


class MissingWebhookError(ValueError):
    """Webhook URL が未設定の場合の例外。"""


class Notifier:
    """Slack Webhook 送信の簡易ラッパー。"""

    def __init__(self, webhook_url: str, environment: str) -> None:
        if not webhook_url:
            raise MissingWebhookError("Slack webhook URL is required")
        self.webhook_url = webhook_url
        self.environment = environment
        self.client = httpx.Client(timeout=5.0)

    @backoff.on_exception(backoff.expo, httpx.HTTPError, max_tries=3, jitter=None)
    def notify(self, event: Mapping[str, Any]) -> None:
        """環境ラベルを付与してSlackへ送信する。"""
        payload = {**event, "env": self.environment}
        try:
            response = self.client.post(
                self.webhook_url,
                headers={"Content-Type": "application/json"},
                content=json.dumps(payload),
            )
            if response.status_code >= 400:
                logger.warning(
                    "Slack notification failed (status=%s, body=%s)",
                    response.status_code,
                    response.text,
                )
                response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("Slack notification failed with network error: %s", exc)
            raise


__all__ = ["Notifier", "MissingWebhookError"]
