"""Feishu/Lark channel — dual transport (webhook / websocket) bidirectional messaging.

[INPUT]
- app.channels.types::ChannelCapabilities, (POS: Provides ArtifactInfo, infer_language, infer_artifact_type.)
- app.channels.core.rate_limit::RateLimitConfig (POS: Rate limiting for inbound messages.)
- app.channels.protocols.route_registrar::HttpMethod, RouteMetadata (POS: Protocol layer for dynamic HTTP route registration. Enables channels to declare their own HTTP endpoints while maintaining framework independence. Business layer implements RouteRegistrar for a specific web framework (e.g. FastAPI via ``myrm-agent-harness[fastapi]``).)
- app.channels.security::SecurityLimits, (POS: Delegates SSRF logic to agent.security.guards.ssrf_guard (single source of truth). Adds media-specific concerns: max-length filenames, path traversal prevention, extension allowlisting.)
- app.channels.core.base::BaseChannel, DedupMode (POS: Channel abstraction layer. All providers inherit this class; Gateway manages them uniformly. Supports outbound (send) and inbound (on_inbound callback) bidirectional communication. Providers may declare credential_spec and from_credentials for self-contained credential management.)
- app.channels.security.errors::WebhookResponseError (POS: Webhook error response layer. Provides RFC 7807 standardized error format, supporting machine-parsable and human-readable output without leaking sensitive data.)

[OUTPUT]
- FeishuChannel: Feishu/Lark Bot channel with dual transport (webhook / we...

[POS]
Feishu/Lark channel — dual transport (webhook / websocket) bidirectional messaging.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import re
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Self

from fastapi import Request
from pydantic import ValidationError

from app.channels.core.allow_policy import AllowPolicy, ChatPolicy
from app.channels.core.base import BaseChannel, DedupMode
from app.channels.core.credentials import credential_field, credential_spec, parse_bool
from app.channels.security.errors import WebhookResponseError
from app.channels.types import (
    ChannelCapabilities,
    ChannelIssue,
    ChannelStatus,
    IssueKind,
    IssueSeverity,
    MediaAttachment,
    MediaType,
    OutboundMessage,
    RenderStyle,
    ReplyContext,
    ToolSummaryDisplay,
)

from .api import FeishuClient
from .cards import (
    build_card_actions,
    build_post_content,
    build_result_card,
    build_thinking_card,
    has_rich_text,
    parse_card_action,
    wrap_text_as_card,
)
from .models import FeishuCardEvent, FeishuWebhookPayload
from .parser import FeishuInboundEvent, extract_message_text, parse_inbound_event

if TYPE_CHECKING:
    from .ws_transport import FeishuWSTransport

logger = logging.getLogger(__name__)

_MAX_TEXT_LENGTH = 4000
_MAX_MEDIA_CONCURRENCY = 3
_CODE_BLOCK_RE = re.compile(r"```[\s\S]*?```")
_UNICODE_TO_FEISHU_EMOJI: dict[str, str] = {
    "\u2705": "DONE",
    "\U0001f44c": "OK",
    "\U0001f44d": "THUMBSUP",
    "\u2764\ufe0f": "HEART",
    "\U0001f389": "JIAYI",
    "\U0001f440": "EYES",
}
# Inbound coverage extends beyond the outbound vocabulary because reaction
# events arrive with the platform's full emoji_type set; aligning with
# ``parse_approval_command``'s three tiers (allow_once / allow_always / deny)
# avoids silent drops when an IM user reacts with the documented vocabulary.
_FEISHU_EMOJI_TO_UNICODE: dict[str, str] = {
    **{v: k for k, v in _UNICODE_TO_FEISHU_EMOJI.items()},
    "THUMBSDOWN": "\U0001f44e",
    "NO": "\u274c",
    "INFINITY": "\u267e",
    "STAR": "\u2b50",
}
_TABLE_RE = re.compile(
    r"((?:^[ \t]*\|.+\|[ \t]*\n)(?:^[ \t]*\|[-:\s|]+\|[ \t]*\n)(?:^[ \t]*\|.+\|[ \t]*\n?)+)",
    re.MULTILINE,
)


class FeishuChannel(BaseChannel):
    """Feishu/Lark Bot channel with dual transport (webhook / websocket).

    Outbound always uses the lightweight httpx-based ``FeishuClient``.
    """

    name = "feishu"

    credential_spec = credential_spec(
        "feishuCredentials",
        app_id=credential_field("appId", "FEISHU_APP_ID"),
        app_secret=credential_field("appSecret", "FEISHU_APP_SECRET"),
        encrypt_key=credential_field("encryptKey", "FEISHU_ENCRYPT_KEY"),
        use_lark=credential_field("useLark", "FEISHU_USE_LARK", "false"),
        render_mode=credential_field("renderMode", "FEISHU_RENDER_MODE", "auto"),
        transport=credential_field("transport", "FEISHU_TRANSPORT", "webhook"),
        verification_token=credential_field("verificationToken", "FEISHU_VERIFICATION_TOKEN"),
        bot_policy=credential_field("botPolicy", "FEISHU_BOT_POLICY", "deny"),
    )
    capabilities = ChannelCapabilities(
        text=True,
        markdown=True,
        media=True,
        file_upload=True,
        buttons=True,
        quick_replies=True,
        select_menus=True,
        interactive_callback=True,
        threads=True,
        edit=True,
        delete=True,
        reactions=True,
        typing_indicator=False,
        max_text_length=_MAX_TEXT_LENGTH,
    )
    render_style = RenderStyle(
        format="markdown",
        max_text_length=_MAX_TEXT_LENGTH,
        tool_summary_display=ToolSummaryDisplay.COMPACT,
    )

    @classmethod
    def from_credentials(cls, creds: dict[str, str]) -> Self:
        transport = creds.get("transport", "webhook")
        if transport not in ("webhook", "websocket"):
            transport = "webhook"
        return cls(
            app_id=creds.get("app_id", ""),
            app_secret=creds.get("app_secret", ""),
            encrypt_key=creds.get("encrypt_key", ""),
            use_lark=parse_bool(creds.get("use_lark", "false")),
            render_mode=creds.get("render_mode", "auto"),
            transport=transport,
            verification_token=creds.get("verification_token", ""),
            bot_policy=creds.get("bot_policy", "deny"),
        )

    def __init__(
        self,
        app_id: str,
        app_secret: str,
        *,
        encrypt_key: str = "",
        use_lark: bool = False,
        render_mode: str = "auto",
        transport: str = "webhook",
        verification_token: str = "",
        bot_policy: str = "deny",
    ) -> None:
        super().__init__()
        self._app_id = app_id
        self._app_secret = app_secret
        self._encrypt_key = encrypt_key
        self._use_lark = use_lark
        self._render_mode = render_mode
        self._transport = transport
        self._verification_token = verification_token
        self._apply_bot_policy(bot_policy)
        self._client = FeishuClient(app_id, app_secret, use_lark=use_lark)
        self._ws_transport: FeishuWSTransport | None = None  # lazy import
        self._streaming_seq: dict[str, int] = {}
        self._streaming_card_ids: dict[str, str] = {}
        self._reaction_ids: dict[str, str] = {}  # message_id → reaction_id for removal

        self._dedup_mode = DedupMode.LRU
        self._dedup_capacity = 1000

    async def start(self) -> None:
        if not self._client.is_configured:
            logger.debug("Feishu credentials not configured; channel idle")
            return
        try:
            await self._client.ensure_token()
            await self._client.fetch_bot_info()
        except Exception as exc:
            logger.warning("FeishuChannel: startup failed: %s", exc)
            self._status = ChannelStatus.ERROR
            await self._client.close()
            return

        if self._transport == "websocket":
            try:
                await self._start_ws_transport()
            except RuntimeError as exc:
                logger.error("FeishuChannel: WebSocket transport failed: %s", exc)
                self._status = ChannelStatus.ERROR
                return

        self._status = ChannelStatus.RUNNING
        self._set_connected(True)
        mode_label = "WebSocket" if self._transport == "websocket" else "Webhook"
        logger.info("FeishuChannel: started (bot=%s, transport=%s)", self._client.bot_open_id, mode_label)

    async def stop(self) -> None:
        for msg_id in list(self._streaming_card_ids):
            try:
                await self._streaming_finalize(msg_id, "")
            except Exception:
                logger.debug("Failed to finalize streaming for %s on stop", msg_id)
        if self._ws_transport:
            await self._ws_transport.stop()
            self._ws_transport = None
        self._reaction_ids.clear()
        self._set_connected(False)
        self._status = ChannelStatus.STOPPED
        await self._client.close()

    async def health_check(self) -> bool:
        if self._status not in (ChannelStatus.RUNNING, ChannelStatus.DEGRADED):
            return False
        ok = await self._client.verify_connectivity()
        if ok:
            self.health.record_success()
        else:
            self.health.record_failure()
        return ok

    async def send(self, msg: OutboundMessage) -> str | None:
        chat_id = msg.recipient_id
        if not chat_id:
            logger.warning("FeishuChannel: no recipient_id, skipping")
            return None

        from .comment_handler import COMMENT_DOC_PREFIX

        if chat_id.startswith(COMMENT_DOC_PREFIX):
            return await self._send_comment_reply(chat_id, msg)

        receive_type = self._resolve_receive_type(chat_id, msg)
        last_msg_id: str | None = None

        for attachment in msg.media:
            mid = await self._send_media(chat_id, receive_type, attachment, msg.reply_to_id)
            if mid:
                last_msg_id = mid

        if msg.content:
            msg_type, content = self._format_outbound(msg)
            mid_str = await self._client.send_message(
                chat_id,
                msg_type,
                content,
                receive_id_type=receive_type,
                reply_in_thread=bool(msg.reply_to_id),
            )
            if mid_str:
                last_msg_id = mid_str

        return last_msg_id

    async def _send_comment_reply(self, recipient_id: str, msg: OutboundMessage) -> str | None:
        """Route outbound message to Feishu document comment API."""
        from .comment_handler import _NO_REPLY_SENTINEL, deliver_comment_reply, parse_comment_recipient

        route = parse_comment_recipient(recipient_id)
        if not route:
            logger.warning("FeishuChannel: malformed comment recipient_id: %s", recipient_id)
            return None

        content = (msg.content or "").strip()
        if not content or _NO_REPLY_SENTINEL in content:
            logger.info("FeishuChannel: comment NO_REPLY, skipping delivery")
            return None

        ok = await deliver_comment_reply(self._client, route, content)
        if ok:
            logger.info("FeishuChannel: comment reply delivered to %s", recipient_id)
        else:
            logger.error("FeishuChannel: comment reply delivery failed for %s", recipient_id)
        return recipient_id if ok else None

    async def send_placeholder(
        self,
        chat_id: str,
        text: str,
        *,
        thread_id: str | None = None,
    ) -> str | None:
        receive_type = self._resolve_receive_type(chat_id)
        card_id = str(uuid.uuid4())
        card = build_thinking_card(text, card_id=card_id)
        content = json.dumps(card, ensure_ascii=False)
        msg_id = await self._client.send_message(
            chat_id,
            "interactive",
            content,
            receive_id_type=receive_type,
        )
        if msg_id:
            ok = await self._client.streaming_card_create(card_id)
            if ok:
                self._streaming_card_ids[msg_id] = card_id
                self._streaming_seq[msg_id] = 1
            else:
                logger.debug("CardKit streaming init failed, will use edit fallback")
        return msg_id

    async def edit_message(self, chat_id: str, message_id: str, text: str) -> None:
        if await self._streaming_update(message_id, text):
            return
        card = wrap_text_as_card(text)
        content = json.dumps(card, ensure_ascii=False)
        await self._client.edit_message(message_id, "interactive", content)

    async def edit_placeholder_message(
        self,
        chat_id: str,
        message_id: str,
        msg: OutboundMessage,
    ) -> None:
        """Replace placeholder with a rich result card; finalize streaming if active."""
        await self._streaming_finalize(message_id, msg.content or "")
        card = self._build_outbound_card(msg)
        content = json.dumps(card, ensure_ascii=False)
        await self._client.edit_message(message_id, "interactive", content)

    async def delete_message(self, chat_id: str, message_id: str) -> None:
        await self._client.delete_message(message_id)

    async def verify(self, request: Request, body: bytes) -> None:
        """SignatureVerifier Protocol: validate Feishu app_id and verification_token.

        Challenge requests (URL verification) skip validation since
        the Feishu platform sends them during webhook registration setup.
        """
        try:
            parsed = json.loads(body)
        except (json.JSONDecodeError, ValueError):
            parsed = {}

        if isinstance(parsed, dict) and "challenge" in parsed:
            return

        trace_id = getattr(request.state, "_webhook_trace_id", "")

        if "header" in parsed and isinstance(parsed["header"], dict):
            event_app_id = parsed["header"].get("app_id", "")
            if event_app_id and event_app_id != self._app_id:
                logger.warning(
                    "Feishu app_id mismatch: expected=%s, got=%s, trace_id=%s",
                    self._app_id,
                    event_app_id,
                    trace_id,
                )
                raise WebhookResponseError(
                    status_code=403,
                    error_type="app-id-mismatch",
                    title="App ID Mismatch",
                    detail=f"Expected app_id {self._app_id}, got {event_app_id}",
                    trace_id=trace_id,
                )

        if self._verification_token:
            body_token = parsed.get("token", "") if isinstance(parsed, dict) else ""
            if not hmac.compare_digest(str(body_token), self._verification_token):
                raise WebhookResponseError(
                    status_code=403,
                    error_type="signature-invalid",
                    title="Invalid Signature",
                    detail="Feishu verification token mismatch",
                    trace_id=trace_id,
                )

    def verify_webhook(self, body: bytes, timestamp: str, nonce: str, signature: str) -> bool:
        """Verify webhook signature: sha256(timestamp + nonce + encrypt_key + body)."""
        if not self._encrypt_key:
            return True
        prefix = (timestamp + nonce + self._encrypt_key).encode("utf-8")
        expected = hashlib.sha256(prefix + body).hexdigest()
        return hmac.compare_digest(expected, signature)

    async def handle_webhook_event(self, event_data: dict[str, object]) -> dict[str, object] | None:
        """Process a Feishu event callback (URL verify / message / card action / comment)."""
        try:
            payload = FeishuWebhookPayload.model_validate(event_data)
        except ValidationError:
            logger.debug("Feishu webhook payload validation failed")
            return None

        if payload.challenge is not None:
            return {"challenge": payload.challenge}

        event_type = payload.header.event_type

        if event_type == "im.message.receive_v1":
            parsed = parse_inbound_event(event_data, bot_open_id=self._client.bot_open_id)
            if parsed and parsed.sender_id != self._client.bot_open_id:
                reply_to = await self._fetch_reply_context(parsed.parent_id)
                content = parsed.content
                media = await self._resolve_inbound_media(parsed)

                sent_at = __import__("time").time()
                create_time = payload.header.create_time
                if create_time:
                    try:
                        sent_at = float(create_time) / 1000.0
                    except (ValueError, TypeError):
                        pass

                inbound = self._build_inbound(
                    sender_id=parsed.sender_id,
                    content=content,
                    sent_at=sent_at,
                    sent_timezone="UTC",
                    chat_id=parsed.chat_id,
                    is_group=parsed.is_group,
                    is_bot=parsed.sender_type in ("bot", "app"),
                    mentioned=parsed.bot_mentioned,
                    media=media,
                    message_id=parsed.message_id,
                    thread_id=parsed.root_id,
                    reply_to=reply_to,
                    metadata={
                        "message_id": parsed.message_id,
                        "msg_type": parsed.msg_type,
                        "image_keys": parsed.image_keys,
                        "media_keys": parsed.media_keys,
                    },
                )
                await self._emit_inbound(inbound)

        elif event_type == "card.action.trigger":
            try:
                card_evt = FeishuCardEvent.model_validate(payload.event)
            except ValidationError:
                logger.debug("Feishu card event validation failed")
                return {"toast": {"type": "info", "content": ""}}

            result = parse_card_action(card_evt.model_dump())
            if result:
                sender_id, chat_id, content, metadata = result
                if sender_id != self._client.bot_open_id and content:
                    sent_at = __import__("time").time()
                    create_time = payload.header.create_time
                    if create_time:
                        try:
                            sent_at = float(create_time) / 1000.0
                        except (ValueError, TypeError):
                            pass

                    inbound = self._build_inbound(
                        sender_id=sender_id,
                        content=content,
                        sent_at=sent_at,
                        sent_timezone="UTC",
                        chat_id=chat_id,
                        is_group=False,
                        mentioned=False,
                        metadata=metadata,
                    )
                    await self._emit_inbound(inbound)
            return {"toast": {"type": "info", "content": ""}}

        elif event_type == "im.message.reaction_created_v1":
            await self._handle_reaction_event(payload.event)

        elif event_type == "drive.notice.comment_add_v1":
            from .comment_handler import CommentHandler

            handler = CommentHandler(self._client, self._client.bot_open_id)
            await handler.handle_comment_event(payload.event, self)

        return None

    async def _handle_reaction_event(self, event: dict[str, object]) -> None:
        """Convert a Feishu im.message.reaction_created_v1 event to InboundMessage."""
        if not isinstance(event, dict):
            return

        message_id = str(event.get("message_id", ""))
        if not message_id:
            return

        reaction_type = event.get("reaction_type")
        emoji_type = ""
        if isinstance(reaction_type, dict):
            emoji_type = str(reaction_type.get("emoji_type", ""))
        if not emoji_type:
            return

        emoji = _FEISHU_EMOJI_TO_UNICODE.get(emoji_type, "")
        if not emoji:
            return

        operator_type = event.get("operator_type")
        sender_id = ""
        if isinstance(operator_type, dict):
            operator_id = operator_type.get("operator_id")
            if isinstance(operator_id, dict):
                sender_id = str(operator_id.get("open_id", ""))
        if not sender_id or sender_id == self._client.bot_open_id:
            return

        inbound = self._build_inbound(
            sender_id=sender_id,
            content=emoji,
            chat_id=sender_id,
            is_group=False,
            mentioned=True,
            message_id=message_id,
            metadata={"reaction": True, "target_message_id": message_id},
        )
        await self._emit_inbound(inbound)

    def collect_issues(self) -> list[ChannelIssue]:
        issues: list[ChannelIssue] = []
        if not self._client.is_configured:
            issues.append(
                ChannelIssue(
                    kind=IssueKind.CONFIG,
                    severity=IssueSeverity.ERROR,
                    message="App ID or App Secret not configured.",
                    fix="Set FEISHU_APP_ID and FEISHU_APP_SECRET, or configure in Settings → Channels → Feishu.",
                )
            )
            return issues
        if self._transport == "websocket":
            from .ws_transport import SDK_AVAILABLE

            if not SDK_AVAILABLE:
                issues.append(
                    ChannelIssue(
                        kind=IssueKind.DEPENDENCY,
                        severity=IssueSeverity.ERROR,
                        message="lark-oapi not installed. Run: uv sync --extra channels-sdk",
                        fix="uv sync --extra channels-sdk",
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

    async def _start_ws_transport(self) -> None:
        """Initialize and start the WebSocket transport."""
        from .ws_transport import FeishuWSTransport

        self._ws_transport = FeishuWSTransport(
            self._app_id,
            self._app_secret,
            use_lark=self._use_lark,
            encrypt_key=self._encrypt_key,
            verification_token=self._verification_token,
        )
        await self._ws_transport.start(on_event=self.handle_webhook_event)

    # ── Private helpers ──────────────────────────────────────────

    _BOT_POLICY_MAP: dict[str, ChatPolicy] = {
        "deny": ChatPolicy.DENY,
        "mention_only": ChatPolicy.MENTION_ONLY,
        "allow": ChatPolicy.ALLOW,
    }

    def _apply_bot_policy(self, raw: str) -> None:
        """Parse bot_policy credential and update allow_policy if needed."""
        policy = self._BOT_POLICY_MAP.get(raw.strip().lower(), ChatPolicy.DENY)
        if policy != ChatPolicy.DENY:
            self.allow_policy = AllowPolicy(
                allowlist=self.allow_policy.allowlist,
                denylist=self.allow_policy.denylist,
                dm_policy=self.allow_policy.dm_policy,
                group_policy=self.allow_policy.group_policy,
                bot_policy=policy,
                chat_overrides=self.allow_policy.chat_overrides,
            )

    @staticmethod
    def _resolve_receive_type(
        chat_id: str,
        msg: OutboundMessage | None = None,
    ) -> str:
        if msg and msg.metadata:
            explicit = msg.metadata.get("receive_type")
            if explicit:
                return str(explicit)
        return "chat_id" if chat_id.startswith("oc_") else "open_id"

    def _format_outbound(self, msg: OutboundMessage) -> tuple[str, str]:
        """Three-level format detection: text → post → card."""
        content = (msg.content or "")[:_MAX_TEXT_LENGTH]
        if self._render_mode == "raw":
            return "text", json.dumps({"text": content}, ensure_ascii=False)
        if self._render_mode == "card" or self._should_use_card(content, msg):
            return "interactive", json.dumps(self._build_outbound_card(msg), ensure_ascii=False)
        if has_rich_text(content):
            return "post", json.dumps(build_post_content(content), ensure_ascii=False)
        return "text", json.dumps({"text": content}, ensure_ascii=False)

    def _should_use_card(self, content: str, msg: OutboundMessage) -> bool:
        from app.channels.types import extract_cron_context

        return bool(
            extract_cron_context(msg)
            or msg.quick_replies
            or msg.components
            or _CODE_BLOCK_RE.search(content)
            or _TABLE_RE.search(content)
            or self._extract_sources(msg)
            or len(content) > 2000
        )

    def _build_outbound_card(self, msg: OutboundMessage) -> dict[str, object]:
        from app.channels.types import extract_cron_context

        cron = extract_cron_context(msg)
        content = (msg.content or "")[:_MAX_TEXT_LENGTH]
        card = build_result_card(
            content,
            title=cron.job_name if cron else "",
            sources=self._extract_sources(msg),
            success=cron.success if cron else None,
            timestamp=datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"),
        )
        actions = build_card_actions(msg.quick_replies, msg.components)
        if actions:
            elems = card.get("elements")
            if isinstance(elems, list):
                elems.extend(actions)
        return card

    @staticmethod
    def _extract_sources(msg: OutboundMessage) -> list[dict[str, object]]:
        if not msg.metadata:
            return []
        sources = msg.metadata.get("sources")
        if isinstance(sources, list):
            return sources  # type: ignore[return-value]
        return []

    async def _send_media(
        self,
        receive_id: str,
        receive_type: str,
        attachment: MediaAttachment,
        reply_to_id: str | None = None,
    ) -> str | None:
        data = await self._download_attachment(attachment)
        if not data:
            return None

        if attachment.media_type == MediaType.IMAGE:
            image_key = await self._client.upload_image(data)
            if not image_key:
                return None
            content = json.dumps({"image_key": image_key})
            msg_type = "image"
        else:
            fname = attachment.filename or f"file.{attachment.media_type.value}"
            file_key = await self._client.upload_file(data, fname)
            if not file_key:
                return None
            content = json.dumps({"file_key": file_key, "file_name": fname})
            msg_type = "file"

        return await self._client.send_message(
            receive_id,
            msg_type,
            content,
            receive_id_type=receive_type,
            reply_in_thread=bool(reply_to_id),
        )

    async def _download_attachment(self, attachment: MediaAttachment) -> bytes | None:
        from pathlib import Path

        if attachment.path:
            try:
                return Path(attachment.path).read_bytes()
            except OSError as exc:
                logger.debug("Failed to read local file %s: %s", attachment.path, exc)
                return None
        return await self._client.download_url(attachment.url) if attachment.url else None

    async def react_to_message(self, chat_id: str, message_id: str, emoji: str) -> None:
        if not message_id:
            return
        try:
            if not emoji:
                reaction_id = self._reaction_ids.pop(message_id, "")
                if reaction_id:
                    await self._client.delete_reaction(message_id, reaction_id)
                return
            feishu_emoji = _UNICODE_TO_FEISHU_EMOJI.get(emoji, emoji)
            rid = await self._client.add_reaction(message_id, feishu_emoji)
            if rid:
                self._reaction_ids[message_id] = rid
        except Exception:
            logger.debug("Feishu reaction failed for %s (emoji=%s)", message_id, emoji)

    async def _fetch_reply_context(self, parent_id: str | None) -> ReplyContext | None:
        """Fetch replied-to message and parse into structured ReplyContext.

        Retrieves parent message via Feishu API, extracts text content and media.
        Returns: ReplyContext with message content, media attachments, sender info.
        """
        if not parent_id:
            return None
        try:
            msg_obj = await self._client.get_message(parent_id)
            if not msg_obj:
                return None

            text = extract_message_text(msg_obj)
            content = text if text else ""

            media_list: list[MediaAttachment] = []
            msg_type = str(msg_obj.get("msg_type", ""))
            if msg_type == "image":
                media_list.append(MediaAttachment(media_type=MediaType.IMAGE))
            elif msg_type == "file":
                media_list.append(MediaAttachment(media_type=MediaType.DOCUMENT))
            elif msg_type == "audio":
                media_list.append(MediaAttachment(media_type=MediaType.AUDIO))
            elif msg_type == "media":
                media_list.append(MediaAttachment(media_type=MediaType.VIDEO))

            sender_info = msg_obj.get("sender", {})
            sender_id = sender_info.get("sender_id", {}).get("open_id") if isinstance(sender_info, dict) else None

            timestamp = None
            create_time = msg_obj.get("create_time")
            if create_time:
                try:
                    timestamp = float(create_time) / 1000.0
                except (ValueError, TypeError):
                    pass

            return ReplyContext(
                message_id=parent_id,
                content=content,
                media=tuple(media_list),
                sender_id=sender_id,
                sender_name=None,
                timestamp=timestamp,
            )
        except Exception:
            logger.debug("Failed to fetch reply context for %s", parent_id)
            return None

    async def _resolve_inbound_media(
        self,
        parsed: FeishuInboundEvent,
    ) -> tuple[MediaAttachment, ...]:
        """Download image/media resources referenced in an inbound event.

        Uses a concurrency semaphore to avoid overwhelming the Feishu API
        with parallel downloads.  Individual download failures are logged
        and skipped so the message is still delivered.
        """
        if not parsed.image_keys and not parsed.media_keys:
            return ()

        sem = asyncio.Semaphore(_MAX_MEDIA_CONCURRENCY)
        tmp_dir = Path(tempfile.gettempdir()) / "feishu_media"
        tmp_dir.mkdir(exist_ok=True)

        async def _download_image(key: str) -> MediaAttachment | None:
            async with sem:
                try:
                    if parsed.message_id:
                        data = await self._client.download_message_resource(
                            parsed.message_id,
                            key,
                            "image",
                        )
                    else:
                        data = await self._client.download_image(key)
                    if not data:
                        return None
                    path = tmp_dir / f"{key}.jpg"
                    path.write_bytes(data)
                    return MediaAttachment(
                        media_type=MediaType.IMAGE,
                        path=str(path),
                        filename=f"{key}.jpg",
                        mime_type="image/jpeg",
                    )
                except Exception:
                    logger.warning("Feishu image download failed: %s", key)
                    return None

        async def _download_file(
            file_key: str,
            file_name: str | None,
        ) -> MediaAttachment | None:
            async with sem:
                try:
                    if not parsed.message_id:
                        return None
                    data = await self._client.download_message_resource(
                        parsed.message_id,
                        file_key,
                        "file",
                    )
                    if not data:
                        return None
                    name = file_name or file_key
                    path = tmp_dir / name
                    path.write_bytes(data)
                    return MediaAttachment(
                        media_type=MediaType.DOCUMENT,
                        path=str(path),
                        filename=name,
                    )
                except Exception:
                    logger.warning("Feishu media download failed: %s", file_key)
                    return None

        tasks: list[asyncio.Task[MediaAttachment | None]] = []
        for key in parsed.image_keys:
            tasks.append(asyncio.create_task(_download_image(key)))
        for file_key, file_name in parsed.media_keys:
            tasks.append(asyncio.create_task(_download_file(file_key, file_name)))

        results = await asyncio.gather(*tasks)
        return tuple(att for att in results if att is not None)

    # ── CardKit streaming ─────────────────────────────────────────

    async def _streaming_update(self, message_id: str, text: str) -> bool:
        """Push incremental streaming; returns False to fall back to edit."""
        card_id = self._streaming_card_ids.get(message_id)
        if not card_id:
            return False
        seq = self._streaming_seq.get(message_id, 1) + 1
        ok = await self._client.streaming_card_update(card_id, text, seq=seq)
        if ok:
            self._streaming_seq[message_id] = seq
        return ok

    async def _streaming_finalize(self, message_id: str, text: str) -> None:
        """Send the final streaming update and clean up the session."""
        card_id = self._streaming_card_ids.pop(message_id, "")
        seq = self._streaming_seq.pop(message_id, 1)
        if not card_id:
            return
        await self._client.streaming_card_update(
            card_id,
            text,
            seq=seq + 1,
            is_final=True,
        )

    def register_routes(self, registrar: object) -> None:
        """Register custom HTTP routes for Feishu webhook.

        Registers POST /webhook endpoint for receiving Feishu event callbacks.
        Handles URL verification challenge, message events, @mention detection.

        Args:
            registrar: RouteRegistrar Protocol implementation (e.g., FastAPIRouteRegistrar)
        """
        from app.channels.core.rate_limit import (
            RateLimitConfig,
        )
        from app.channels.protocols.route_registrar import (
            HttpMethod,
            RouteMetadata,
        )
        from app.channels.security import (
            SecurityLimits,
            SecurityProtocols,
            WebhookResponseError,
            WebhookSecurityMiddleware,
        )

        middleware = WebhookSecurityMiddleware(
            limits=SecurityLimits(
                body_limit_pre_auth=10_000,
                body_limit_post_auth=10_000,
                read_timeout_seconds=5.0,
            ),
            protocols=SecurityProtocols(signature_verifier=self),
        )

        async def webhook_handler(request):
            """Handle Feishu webhook events."""
            import json

            try:
                ctx = await middleware.process_request(request, "feishu")

                if ctx.parsed_data is None:

                    class _ErrorResponse:
                        status_code = 400
                        headers = {}
                        body = b'{"error": "Invalid JSON"}'

                    return _ErrorResponse()

                result = await self.handle_webhook_event(ctx.parsed_data)
                if result is not None:

                    class _JsonResponse:
                        status_code = 200
                        headers = {}
                        body = json.dumps(result).encode("utf-8")

                    return _JsonResponse()

            except WebhookResponseError as e:

                class _WebhookErrorResponse:
                    status_code = e.status_code
                    headers = {}
                    body = json.dumps(e.to_dict()).encode("utf-8")

                return _WebhookErrorResponse()
            except Exception as e:
                logger.warning("Feishu webhook error: %s", e, exc_info=True)

                class _InternalErrorResponse:
                    status_code = 500
                    headers = {}
                    body = json.dumps({"ok": False, "error": "Internal error"}).encode("utf-8")

                return _InternalErrorResponse()

            class _SuccessResponse:
                status_code = 200
                headers = {}
                body = b'{"ok": true}'

            return _SuccessResponse()

        registrar.add_route(
            method=HttpMethod.POST,
            path="webhook",
            handler=webhook_handler,
            metadata=RouteMetadata(
                description="Receive Feishu event callback (URL verification, messages, @mentions)",
                requires_auth=False,
                rate_limit_policy=RateLimitConfig(max_requests=60, window_seconds=60),
            ),
        )
