"""Asynchronous webhook notifier for A2A push notifications.

Dispatches HMAC-SHA256 signed webhook events to caller URLs
with exponential backoff and replay-resistant headers.

[INPUT]
- WebhookNotification, push_url, push_secret

[OUTPUT]
- Delivery success boolean and audit telemetry

[POS]
Outbound push notification worker for A2A Provider Server.
"""

from __future__ import annotations

import asyncio
import json
import logging

import httpx
from myrm_agent_harness.toolkits.a2a.security import compute_hmac_signature
from myrm_agent_harness.toolkits.a2a.types import WebhookNotification

logger = logging.getLogger(__name__)


class A2AWebhookSender:
    """Delivers signed push events to external A2A caller endpoints."""

    def __init__(self, timeout_sec: float = 10.0, max_retries: int = 2) -> None:
        self.timeout_sec = timeout_sec
        self.max_retries = max_retries

    async def deliver(
        self,
        push_url: str,
        notification: WebhookNotification,
        push_secret: str | None = None,
    ) -> bool:
        """Send notification JSON to push_url with HMAC headers."""
        if not push_url.startswith(("http://", "https://")):
            logger.warning("Invalid A2A webhook scheme for push_url: %s", push_url)
            return False

        payload_bytes = json.dumps(
            notification.model_dump(by_alias=True), ensure_ascii=False
        ).encode("utf-8")
        timestamp_str = str(notification.timestamp)

        headers: dict[str, str] = {
            "Content-Type": "application/json",
            "X-A2A-Delivery-ID": notification.delivery_id,
            "X-A2A-Timestamp": timestamp_str,
        }

        if push_secret:
            sig = compute_hmac_signature(push_secret, payload_bytes, timestamp_str)
            headers["X-A2A-Signature"] = sig

        for attempt in range(self.max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout_sec) as client:
                    resp = await client.post(push_url, content=payload_bytes, headers=headers)
                    if resp.is_success:
                        logger.info(
                            "A2A webhook delivered to %s (delivery_id=%s, code=%d)",
                            push_url,
                            notification.delivery_id,
                            resp.status_code,
                        )
                        return True
                    logger.warning(
                        "A2A webhook received non-success code %d from %s (attempt %d/%d)",
                        resp.status_code,
                        push_url,
                        attempt + 1,
                        self.max_retries + 1,
                    )
            except Exception as e:
                logger.warning(
                    "A2A webhook delivery attempt %d failed for %s: %s",
                    attempt + 1,
                    push_url,
                    e,
                )

            if attempt < self.max_retries:
                await asyncio.sleep(0.5 * (2**attempt))

        return False
