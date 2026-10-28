"""iMessage channel — via BlueBubbles HTTP API bridge.

Inbound: webhook callback → _parse_message → _emit_inbound
Outbound: REST API (text + multipart attachment) with Tapback reactions

[INPUT]
- channels.providers.imessage.outbound (POS: text, attachment and Tapback requests to BlueBubbles)
- channels.providers.imessage.diagnostics::collect_imessage_issues (POS: configuration and connection diagnosis)
- channels.core.attachment_delivery::deliver_attachments (POS: per-attachment delivery with aggregated failure)
- channels.core.base::BaseChannel (POS: Channel abstract base)
- channels.core.reaction_ledger::ReactionLedger (POS: remembers the reaction added per message so an empty emoji removes it)

[OUTPUT]
- IMessageChannel: iMessage bidirectional Channel (via BlueBubbles macOS bridge)

[POS]
iMessage channel via BlueBubbles API. Text/media send, Tapback reactions,
webhook authentication, structured diagnostics.
"""

from __future__ import annotations

import asyncio
import hmac
import logging
from functools import partial

import httpx

from app.channels.core.attachment_delivery import deliver_attachments
from app.channels.core.base import BaseChannel
from app.channels.core.credentials import credential_field, credential_spec
from app.channels.core.exceptions import ChannelConnectionError, ChannelSendError
from app.channels.core.reaction_ledger import ReactionLedger
from app.channels.rendering.renderer import render
from app.channels.types import (
    ChannelCapabilities,
    ChannelIssue,
    ChannelStatus,
    InboundMessage,
    OutboundMessage,
    RenderStyle,
    ToolSummaryDisplay,
    reaction_key,
)

from .diagnostics import collect_imessage_issues
from .helpers import (
    CHANNEL_NAME,
    MAX_TEXT_LENGTH,
    TAPBACK_MAP,
    TAPBACK_REMOVE_PREFIX,
    compile_mention_patterns,
    quote_guid,
)
from .outbound import post_tapback, send_attachment, send_text
from .parser import parse_message
from .webhook import register_webhook, unregister_webhook

logger = logging.getLogger(__name__)


class IMessageChannel(BaseChannel):
    """iMessage channel via BlueBubbles API.

    Inbound: webhook callback (new-message events)
    Outbound: REST API (text + multipart attachment + Tapback reactions)
    """

    name = CHANNEL_NAME
    credential_spec = credential_spec(
        "imessageCredentials",
        api_url=credential_field("apiUrl", "IMESSAGE_API_URL"),
        password=credential_field("password", "IMESSAGE_PASSWORD"),
        webhook_url=credential_field("webhookUrl", "IMESSAGE_WEBHOOK_URL", required=False),
        mention_patterns=credential_field("mentionPatterns", "IMESSAGE_MENTION_PATTERNS", required=False),
    )
    capabilities = ChannelCapabilities(
        text=True,
        media=True,
        file_upload=True,
        reactions=True,
        reaction_glyphs=frozenset(TAPBACK_MAP),
        typing_keepalive_interval=55.0,
        max_text_length=MAX_TEXT_LENGTH,
    )
    render_style = RenderStyle(
        format="text",
        max_text_length=MAX_TEXT_LENGTH,
        tool_summary_display=ToolSummaryDisplay.COMPACT,
    )

    def __init__(
        self,
        api_url: str,
        password: str,
        webhook_url: str = "",
        mention_patterns: tuple[str, ...] | list[str] | str | None = None,
    ) -> None:
        super().__init__()
        self._api_url = api_url.rstrip("/")
        self._password = password
        self._webhook_url = webhook_url.strip() if webhook_url else ""
        self._mention_patterns = compile_mention_patterns(mention_patterns)
        self._http = httpx.AsyncClient()
        self._reactions = ReactionLedger()
        self._private_api_available = False
        self._helper_connected = False

    @property
    def private_api_available(self) -> bool:
        return self._private_api_available

    @property
    def helper_connected(self) -> bool:
        return self._helper_connected

    @property
    def _private_api_ready(self) -> bool:
        """BlueBubbles refuses Tapbacks, typing, read receipts and quoted replies unless both hold."""
        return self._private_api_available and self._helper_connected

    # ── Lifecycle ─────────────────────────────────────────────────────

    async def start(self) -> None:
        if not self._api_url:
            logger.info("iMessage API URL not configured; channel idle")
            return

        max_retries = 5
        base_delay = 2.0

        for attempt in range(max_retries):
            try:
                resp = await self._http.get(
                    f"{self._api_url}/api/v1/server/info",
                    params={"password": self._password},
                    timeout=5.0,
                )
                if resp.status_code == 200:
                    self._detect_private_api(resp)
                    self._status = ChannelStatus.RUNNING
                    self._set_connected(True)
                    await self._register_webhook()
                    logger.info("IMessageChannel: started successfully (private_api=%s)", self._private_api_available)
                    return
                else:
                    logger.warning(
                        "IMessageChannel: BlueBubbles bridge returned HTTP %d (attempt %d/%d)",
                        resp.status_code,
                        attempt + 1,
                        max_retries,
                    )
            except Exception as exc:
                logger.warning(
                    "IMessageChannel: BlueBubbles bridge unreachable: %s (attempt %d/%d)", exc, attempt + 1, max_retries
                )

            if attempt < max_retries - 1:
                delay = base_delay * (2**attempt)
                logger.info("IMessageChannel: Retrying connection in %.1fs...", delay)
                await asyncio.sleep(delay)

        self._status = ChannelStatus.DEGRADED
        self._set_connected(False)
        logger.error(
            "IMessageChannel: cannot connect to BlueBubbles bridge at %s after %d attempts",
            self._api_url,
            max_retries,
        )
        raise ChannelConnectionError(
            f"Failed to connect to BlueBubbles bridge at {self._api_url} after {max_retries} attempts",
            channel=self.name,
        )

    async def stop(self) -> None:
        await self._unregister_webhook()
        self._set_connected(False)
        self._status = ChannelStatus.STOPPED
        await self._http.aclose()
        logger.info("IMessageChannel: stopped")

    async def health_check(self) -> bool:
        if self._status not in (ChannelStatus.RUNNING, ChannelStatus.DEGRADED):
            return False
        try:
            resp = await self._http.get(
                f"{self._api_url}/api/v1/server/info",
                params={"password": self._password},
                timeout=10.0,
            )
            ok = resp.status_code == 200
            if ok:
                self._detect_private_api(resp)
                self.health.record_success()
            else:
                self.health.record_failure(f"HTTP {resp.status_code}")
            return ok
        except Exception as exc:
            self.health.record_failure(str(exc))
            return False

    def _detect_private_api(self, resp: httpx.Response) -> None:
        """Take private_api and helper_connected from a BlueBubbles server/info response.

        Called at start and by every health check, so the flags follow the server (the helper may connect after
        start or drop later). A body that cannot be read keeps the last known state.
        """
        try:
            data = resp.json().get("data", {})
        except Exception as exc:
            logger.debug("IMessageChannel: server/info body unreadable, keeping Private API state: %s", exc)
            return
        if isinstance(data, dict):
            self._private_api_available = bool(data.get("private_api"))
            self._helper_connected = bool(data.get("helper_connected"))

    async def _mark_read(self, chat_guid: str) -> None:
        """Send a read receipt for the chat (requires Private API + helper)."""
        if not self._private_api_ready or not chat_guid:
            return
        try:
            await self._http.post(
                f"{self._api_url}/api/v1/chat/{quote_guid(chat_guid)}/read",
                params={"password": self._password},
                timeout=5.0,
            )
        except Exception:
            pass

    # ── Webhook Auto-Registration ────────────────────────────────────

    async def _register_webhook(self) -> None:
        await register_webhook(self._http, self._api_url, self._password, self._webhook_url)

    async def _unregister_webhook(self) -> None:
        await unregister_webhook(self._http, self._api_url, self._password, self._webhook_url)

    # ── Typing Indicator ──────────────────────────────────────────────

    async def start_typing(self, chat_id: str) -> None:
        if not self._private_api_ready:
            return
        try:
            await self._http.post(
                f"{self._api_url}/api/v1/chat/{quote_guid(chat_id)}/typing",
                params={"password": self._password},
                timeout=5.0,
            )
        except Exception as exc:
            logger.debug("iMessage start_typing failed for %s: %s", chat_id[:20], exc)

    async def stop_typing(self, chat_id: str) -> None:
        if not self._private_api_ready:
            return
        try:
            await self._http.request(
                "DELETE",
                f"{self._api_url}/api/v1/chat/{quote_guid(chat_id)}/typing",
                params={"password": self._password},
                timeout=5.0,
            )
        except Exception as exc:
            logger.debug("iMessage stop_typing failed for %s: %s", chat_id[:20], exc)

    # ── Inbound ───────────────────────────────────────────────────────

    async def handle_webhook(self, body: dict[str, object]) -> None:
        """Process a BlueBubbles webhook event."""
        event_type = body.get("type", "")
        if event_type != "new-message":
            return
        data = body.get("data", {})
        if not isinstance(data, dict):
            return
        msg = self._parse_message(data)
        if msg:
            await self._emit_inbound(msg)
            if msg.chat_id:
                asyncio.create_task(self._mark_read(msg.chat_id))

    def verify_webhook_password(self, body: dict[str, object]) -> bool:
        """Verify BlueBubbles webhook password (timing-safe comparison)."""
        if not self._password:
            return True
        incoming = str(body.get("password", ""))
        return hmac.compare_digest(incoming, self._password)

    def _parse_message(self, data: dict[str, object]) -> InboundMessage | None:
        return parse_message(
            data,
            self._api_url,
            self._password,
            self._build_inbound,
            mention_patterns=self._mention_patterns,
        )

    # ── Outbound ──────────────────────────────────────────────────────

    async def send(self, msg: OutboundMessage) -> str | None:
        chat_guid = msg.recipient_id or ""
        if not chat_guid:
            raise ChannelSendError("iMessage message has no recipient", channel=self.name, retriable=False)

        last_guid: str | None = None
        # Quoting needs the Private API helper; without it a reply is sent as a plain message.
        quote = msg.reply_to_id if msg.reply_to_id and self._private_api_ready else None

        if msg.content:
            for chunk in render(msg, self.render_style):
                last_guid = await send_text(self._http, self._api_url, self._password, chat_guid, chunk, quote=quote) or last_guid
                quote = None  # only the first chunk quotes the message

        attachment_guid = await deliver_attachments(
            self.name,
            msg.media,
            partial(send_attachment, self._http, self._api_url, self._password, chat_guid),
            text_delivered=bool(msg.content),
        )
        return last_guid or attachment_guid

    # ── Reactions ─────────────────────────────────────────────────────

    async def react_to_message(
        self,
        chat_id: str,
        message_id: str,
        emoji: str,
    ) -> None:
        """Send a Tapback via the BlueBubbles Private API; an empty emoji removes the one this channel sent.

        Without the Private API and its helper BlueBubbles refuses every Tapback, so none is sent (the channel
        diagnostics report the cause); a skipped removal keeps its ledger entry, so a later removal still takes
        the Tapback off.
        """
        if not self._private_api_ready:
            return
        post = partial(post_tapback, self._http, self._api_url, self._password, chat_id, message_id)
        if emoji:
            tapback = TAPBACK_MAP.get(reaction_key(emoji))
            if tapback is None:
                return
            await post(tapback)
            self._reactions.remember(chat_id, message_id, tapback)
            return
        sent = self._reactions.take(chat_id, message_id)
        if sent:
            await post(f"{TAPBACK_REMOVE_PREFIX}{sent}")

    # ── Diagnostics ───────────────────────────────────────────────────

    def collect_issues(self) -> list[ChannelIssue]:
        return collect_imessage_issues(
            api_url=self._api_url,
            password=self._password,
            status=self._status,
            last_error=self.health.last_error,
            private_api_available=self._private_api_available,
            helper_connected=self._helper_connected,
        )
