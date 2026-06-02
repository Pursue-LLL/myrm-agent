"""Google Chat channel — Webhook-based bidirectional messaging.

Inbound: HTTP Webhook (Google pushes events to our endpoint).
Outbound: Google Chat API v1 with Service Account auth.

Supports DM and Space (group) messages, message editing and deletion,
and thread-based replies.

[INPUT]
- app.channels.core.base::BaseChannel (POS: Channel base class with unified send/receive contract.)
- app.channels.types::ChannelCapabilities (POS: Channel capability and artifact type definitions.)
- app.channels.core.exceptions::ChannelSendError (POS: Channel exception hierarchy.)
- app.channels.security.errors::WebhookResponseError (POS: RFC 7807 webhook error responses.)

[OUTPUT]
- GoogleChatChannel: Google Chat bidirectional channel (Webhook inbound + Chat API outbound).

[POS]
app.channels.providers.googlechat.channel — Google Chat Webhook-based bidirectional messaging.
"""

from __future__ import annotations

import logging

import httpx
from fastapi import Request

from app.channels import BaseChannel, InboundMessage, OutboundMessage
from app.channels.core.credentials import credential_field, credential_spec
from app.channels.core.exceptions import ChannelSendError
from app.channels.rendering.renderer import render
from app.channels.security.errors import WebhookResponseError
from app.channels.types import (
    ChannelCapabilities,
    ChannelIssue,
    ChannelStatus,
    IssueKind,
    IssueSeverity,
    RenderStyle,
    ToolSummaryDisplay,
)

from .api import GoogleChatClient

logger = logging.getLogger(__name__)

_MAX_MSG_LENGTH = 4096


class GoogleChatChannel(BaseChannel):
    """Google Chat channel using Webhook inbound + Chat API outbound.

    Inbound: Google pushes events to POST /channels/googlechat/webhook.
    Outbound: Chat API v1 via Service Account JWT auth.
    """

    name = "googlechat"
    credential_spec = credential_spec(
        "googlechatCredentials",
        service_account_json=credential_field("serviceAccountJson", "GOOGLE_CHAT_SERVICE_ACCOUNT_JSON"),
    )
    capabilities = ChannelCapabilities(
        text=True,
        markdown=False,
        media=False,
        buttons=False,
        threads=True,
        edit=True,
        delete=True,
        max_text_length=_MAX_MSG_LENGTH,
    )
    render_style = RenderStyle(
        format="plaintext",
        max_text_length=_MAX_MSG_LENGTH,
        tool_summary_display=ToolSummaryDisplay.COMPACT,
    )

    def __init__(self, service_account_json: str, webhook_audience: str = "") -> None:
        super().__init__()
        self._api = GoogleChatClient(service_account_json)
        self._webhook_audience = webhook_audience

    async def start(self) -> None:
        if not self._api.is_configured:
            logger.debug("Google Chat: no service account configured; channel idle")
            return

        ok = await self._api.verify_token()
        if ok:
            await super().start()
            logger.info("Google Chat: authenticated successfully")
        else:
            self._status = ChannelStatus.DEGRADED
            logger.warning("Google Chat: authentication failed; channel degraded")

    async def stop(self) -> None:
        await self._api.close()
        await super().stop()

    async def verify(self, request: Request, body: bytes) -> None:
        """SignatureVerifier Protocol: validate Google Chat bearer token (OIDC/JWT)."""
        audience = self._webhook_audience
        if not audience:
            return

        auth_header = request.headers.get("authorization", "")
        if not auth_header.startswith("Bearer "):
            trace_id = getattr(request.state, "_webhook_trace_id", "")
            raise WebhookResponseError(
                status_code=401,
                error_type="signature-invalid",
                title="Missing Bearer Token",
                detail="Google Chat webhook requires a Bearer token",
                trace_id=trace_id,
            )

        from .api import verify_google_chat_bearer

        token = auth_header[7:]
        if not await verify_google_chat_bearer(token, audience):
            trace_id = getattr(request.state, "_webhook_trace_id", "")
            raise WebhookResponseError(
                status_code=401,
                error_type="signature-invalid",
                title="Invalid Signature",
                detail="Google Chat bearer token verification failed",
                trace_id=trace_id,
            )

    # ── Inbound — Webhook ─────────────────────────────────────────

    async def handle_webhook(self, event: dict[str, object]) -> None:
        """Process an incoming Google Chat event (MESSAGE type only)."""
        if str(event.get("type", "")) != "MESSAGE":
            return

        message = event.get("message")
        if not isinstance(message, dict):
            return

        space = event.get("space")
        if not isinstance(space, dict):
            return

        sender = event.get("user")
        if not isinstance(sender, dict):
            return

        text = str(message.get("argumentText", "") or message.get("text", "")).strip()
        if not text:
            return

        sender_name = str(sender.get("displayName", ""))
        sender_id = str(sender.get("name", ""))
        space_name = str(space.get("name", ""))
        space_type = str(space.get("type", ""))
        is_group = space_type in ("ROOM", "SPACE")

        thread = message.get("thread")
        thread_id: str | None = None
        if isinstance(thread, dict):
            thread_id = str(thread.get("name", ""))

        msg_name = str(message.get("name", ""))

        sent_at = __import__("time").time()
        create_time = message.get("createTime")
        if create_time:
            try:
                from datetime import datetime

                dt = datetime.fromisoformat(str(create_time).replace("Z", "+00:00"))
                sent_at = dt.timestamp()
            except (ValueError, TypeError):
                pass

        inbound = InboundMessage(
            channel="googlechat",
            sender_id=sender_id,
            content=text,
            sent_at=sent_at,
            sent_timezone="UTC",
            chat_id=space_name,
            sender_name=sender_name or None,
            is_group=is_group,
            mentioned=True,
            thread_id=thread_id,
            metadata={
                "platform": "googlechat",
                "space_type": space_type,
                "message_name": msg_name,
            },
            message_id=msg_name or None,
        )
        await self._emit_inbound(inbound)

    # ── Outbound ──────────────────────────────────────────────────

    async def send(self, msg: OutboundMessage) -> str | None:
        space = msg.recipient_id
        if not space or not msg.content:
            return None

        thread_key: str | None = msg.thread_id
        if not thread_key and msg.metadata and isinstance(msg.metadata, dict):
            thread_key = str(msg.metadata.get("thread_id", "")) or None

        last_name: str | None = None
        try:
            for chunk in render(msg, self.render_style):
                result = await self._api.send_message(space, chunk, thread_key=thread_key)
                if isinstance(result, dict):
                    name = result.get("name")
                    if name:
                        last_name = str(name)
            self.health.record_success()
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            self.health.record_failure(f"HTTP {status}")
            raise ChannelSendError(
                f"Google Chat send failed: HTTP {status}",
                channel=self.name,
                status_code=status,
                retriable=status >= 500 or status == 429,
            ) from exc
        except Exception as exc:
            self.health.record_failure(str(exc))
            raise ChannelSendError(
                f"Google Chat send failed: {exc}",
                channel=self.name,
            ) from exc

        return last_name

    async def send_placeholder(self, chat_id: str, text: str, *, thread_id: str | None = None) -> str | None:
        try:
            result = await self._api.send_message(chat_id, text, thread_key=thread_id)
            return str(result.get("name", ""))
        except Exception as exc:
            logger.warning("Google Chat placeholder failed: %s", exc)
            return None

    async def edit_message(self, chat_id: str, message_id: str, text: str) -> None:
        try:
            await self._api.update_message(message_id, text)
        except Exception as exc:
            logger.warning("Google Chat edit failed: %s", exc)

    async def delete_message(self, chat_id: str, message_id: str) -> None:
        try:
            await self._api.delete_message(message_id)
        except Exception as exc:
            logger.warning("Google Chat delete failed: %s", exc)

    # ── Health ────────────────────────────────────────────────────

    async def health_check(self) -> bool:
        if not self._api.is_configured:
            return False
        try:
            ok = await self._api.verify_token()
            if ok:
                self.health.record_success()
            else:
                self.health.record_failure("Token verification failed")
            return ok
        except Exception as exc:
            self.health.record_failure(str(exc))
            return False

    def collect_issues(self) -> list[ChannelIssue]:
        issues: list[ChannelIssue] = []
        if not self._api.is_configured:
            issues.append(
                ChannelIssue(
                    kind=IssueKind.CONFIG,
                    severity=IssueSeverity.ERROR,
                    message="Service Account JSON not configured.",
                    fix="Set GOOGLECHAT_SERVICE_ACCOUNT_JSON, or configure in Settings → Channels → Google Chat.",
                )
            )
            return issues
        if self._status == ChannelStatus.DEGRADED:
            issues.append(
                ChannelIssue(
                    kind=IssueKind.CONFIG,
                    severity=IssueSeverity.WARNING,
                    message="Authentication failed. Channel running in degraded mode.",
                    fix="Verify Service Account JSON is valid and has Chat API permissions.",
                )
            )
        if self.health.last_error:
            issues.append(
                ChannelIssue(
                    kind=IssueKind.RUNTIME,
                    severity=IssueSeverity.ERROR,
                    message=self.health.last_error,
                )
            )
        return issues
