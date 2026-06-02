"""Generic webhook channel — POST JSON to any URL.

Sends a structured JSON payload to the URL specified in
``msg.recipient_id``.  Designed for Cron result delivery to external
systems (n8n, Zapier, custom webhooks) and third-party integrations.

[INPUT]
- channels.core.base::BaseChannel (POS: Channel abstract base class)
- channels.types::OutboundMessage, (POS: Provides ArtifactInfo, infer_language, infer_artifact_type.)
  ToolSummaryDisplay, extract_cron_context

[OUTPUT]
- WebhookChannel: generic webhook push Channel

[POS]
Generic webhook push channel. Converts OutboundMessage to JSON POST to user-specified URL.
Suitable for third-party integrations like n8n, Zapier, or platforms without a dedicated Channel.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

import httpx

from app.channels.core.base import BaseChannel
from app.channels.core.exceptions import ChannelSendError
from app.channels.types import (
    ChannelCapabilities,
    OutboundMessage,
    RenderStyle,
    ToolSummaryDisplay,
    extract_cron_context,
)

logger = logging.getLogger(__name__)

_TIMEOUT = 15.0


class WebhookChannel(BaseChannel):
    """POST structured JSON to an arbitrary webhook URL.

    The ``httpx.AsyncClient`` is lazily created on first ``send()`` and
    closed in ``stop()`` to enable TCP connection reuse across deliveries.
    """

    name = "webhook"
    capabilities = ChannelCapabilities(
        markdown=True,
        typing_indicator=False,
        max_text_length=10_000,
    )
    render_style = RenderStyle(
        format="markdown",
        use_emoji=True,
        max_text_length=10_000,
        supports_code_fence=True,
        supports_links=True,
        supports_tables=True,
        tool_summary_display=ToolSummaryDisplay.COMPACT,
    )

    def __init__(self) -> None:
        super().__init__()
        self._client: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=_TIMEOUT)
        return self._client

    async def stop(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
        await super().stop()

    async def send(self, msg: OutboundMessage) -> str | None:
        url = msg.recipient_id
        if not url:
            logger.warning("WebhookChannel: no URL provided, skipping")
            return None

        payload = self._build_payload(msg)

        try:
            client = self._get_client()
            resp = await client.post(
                url,
                content=json.dumps(payload, ensure_ascii=False),
                headers={"Content-Type": "application/json"},
            )
            if resp.status_code >= 400:
                self.health.record_failure(f"HTTP {resp.status_code}")
                raise ChannelSendError(
                    f"Webhook POST failed: HTTP {resp.status_code}",
                    channel="webhook",
                    status_code=resp.status_code,
                    retriable=resp.status_code >= 500,
                )
        except ChannelSendError:
            raise
        except Exception as exc:
            self.health.record_failure(str(exc))
            raise ChannelSendError(
                f"Webhook POST error: {exc}",
                channel="webhook",
                retriable=True,
            ) from exc

        self.health.record_success()
        logger.debug("WebhookChannel: delivered to %s", url[:60])
        return self._extract_message_id(resp)

    def _build_payload(self, msg: OutboundMessage) -> dict[str, object]:
        payload: dict[str, object] = {
            "content": msg.content or "",
            "timestamp": datetime.now(UTC).isoformat(),
        }

        cron = extract_cron_context(msg)
        if cron:
            payload["cron"] = {
                "job_name": cron.job_name,
                "success": cron.success,
            }

        if msg.media:
            payload["media"] = [
                {
                    "type": att.media_type.value,
                    "url": att.url,
                    "filename": att.filename,
                    "caption": att.caption,
                }
                for att in msg.media
            ]

        if msg.reasoning:
            payload["reasoning"] = msg.reasoning

        if msg.tool_steps:
            payload["tool_steps"] = [{"name": step.name, "status": step.status} for step in msg.tool_steps]

        if msg.reply_to_id:
            payload["reply_to_id"] = msg.reply_to_id

        if msg.metadata:
            sources = msg.metadata.get("sources")
            if sources:
                payload["sources"] = sources
            steps = msg.metadata.get("progressSteps")
            if steps:
                payload["steps"] = steps

        return payload

    @staticmethod
    def _extract_message_id(resp: httpx.Response) -> str | None:
        """Try to parse a message ID from the webhook response body."""
        try:
            body = resp.json()
            if isinstance(body, dict):
                for key in ("id", "message_id", "messageId"):
                    val = body.get(key)
                    if isinstance(val, (str, int)):
                        return str(val)
        except (json.JSONDecodeError, ValueError):
            pass
        return None
