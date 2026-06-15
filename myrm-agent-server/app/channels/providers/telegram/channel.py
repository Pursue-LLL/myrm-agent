"""Telegram Bot channel — bidirectional messaging via Bot API.

Inbound: getUpdates/Webhook -> _parse_update -> _pre_emit_hook -> _buffer_or_emit -> _emit_inbound
  - DM: direct messages; Group: mention detection via entities
  - Media groups: debounce + hard deadline aggregation into single InboundMessage
  - Supports message, edited_message, callback_query (qr/act/sel/ag), sticker
  - _pre_emit_hook may return None to suppress messages handled as bot commands (/agent)
Outbound: sendMessage/sendPhoto/sendDocument/sendVoice/sendAudio/sendVideo (HTML parse_mode)
Forum Topics: create/rename/close/reopen + auto-topic creation with per-user dedup and name sync

[INPUT]
- channels.core.base::BaseChannel (POS: Abstract base for channel providers.)
- channels.types::OutboundMessage, InboundMessage
- services.agent.agent_service::AgentService (POS: 业务层Agent服务。)

[OUTPUT]
- TelegramChannel: Telegram Bot bidirectional Channel (polling + webhook)

[POS]
Telegram Bot channel implementation. Supports DM and group chat, media group
debounce aggregation, webhook/polling dual mode, inline keyboard rendering,
Markdown -> HTML conversion, message splitting, command registration, /agent
inline picker (agent switching via Inline Keyboard), diagnostics,
and Forum Topic management (create/rename/close/reopen, auto-topic, name sync).
"""

from __future__ import annotations

import asyncio
import dataclasses
import hmac
import logging
from pathlib import Path
from typing import Self

from fastapi import Request

from app.channels.core.allow_policy import AllowPolicy, ChatPolicy
from app.channels.core.base import BaseChannel
from app.channels.core.credentials import (
    credential_field,
)
from app.channels.core.credentials import (
    credential_spec as build_credential_spec,
)
from app.channels.providers.telegram.notification import (
    notification_kwargs,
)
from app.channels.reliability.retry import RetryConfig
from app.channels.rendering.renderer import render
from app.channels.security.errors import WebhookResponseError
from app.channels.types import (
    ChannelCapabilities,
    ChannelIssue,
    ChannelStatus,
    InboundMessage,
    IssueKind,
    IssueSeverity,
    OutboundMessage,
    ReasoningDisplay,
    RenderStyle,
    ToolSummaryDisplay,
)
from app.channels.types.notification import (
    ChannelNotificationMode,
    parse_notification_mode,
)

from .api import TelegramApiError, TelegramClient
from app.channels.i18n import get_text
from .helpers import (
    MAX_TEXT_LENGTH,
    BotCommand,
    _MediaGroupBuffer,
    build_inline_keyboard,
    send_media_attachment,
)
from .html_converter import md_to_telegram_html, split_message
from .inbound import _ALLOWED_UPDATES, TelegramInboundMixin

logger = logging.getLogger(__name__)

_MIN_DRAFT_CHARS = 20
_RICH_MAX_TEXT_LENGTH = 32000  # practical limit below 32768 to leave headroom


class TelegramChannel(TelegramInboundMixin, BaseChannel):
    """Telegram Bot channel with long-polling/webhook and message sending.

    Uses ``TelegramClient`` for all API calls. Outbound text is converted
    from Markdown to Telegram HTML for reliable formatting.
    """

    name = "telegram"
    credential_spec = build_credential_spec(
        "telegramCredentials",
        token=credential_field("botToken", "TELEGRAM_BOT_TOKEN"),
        webhook_url=credential_field("webhookUrl", "TELEGRAM_WEBHOOK_URL"),
        bot_policy=credential_field("botPolicy", "TELEGRAM_BOT_POLICY", default="deny"),
        auto_topic=credential_field("autoTopic", "TELEGRAM_AUTO_TOPIC", default="false", required=False, is_sensitive=False),
        notifications_mode=credential_field(
            "notificationsMode",
            "TELEGRAM_NOTIFICATIONS_MODE",
            default="important",
            required=False,
            is_sensitive=False,
        ),
    )
    capabilities = ChannelCapabilities(
        text=True,
        markdown=True,
        media=True,
        voice_message=True,
        file_upload=True,
        buttons=True,
        quick_replies=True,
        select_menus=True,
        interactive_callback=True,
        threads=True,
        edit=True,
        delete=True,
        reactions=True,
        typing_indicator=True,
        max_text_length=MAX_TEXT_LENGTH,
    )
    render_style = RenderStyle(
        format="markdown",
        max_text_length=MAX_TEXT_LENGTH,
        reasoning_display=ReasoningDisplay.COLLAPSED,
        tool_summary_display=ToolSummaryDisplay.COMPACT,
    )
    _rich_render_style = RenderStyle(
        format="markdown",
        max_text_length=_RICH_MAX_TEXT_LENGTH,
        supports_latex=True,
        supports_tables=True,
        reasoning_display=ReasoningDisplay.COLLAPSED,
        tool_summary_display=ToolSummaryDisplay.COMPACT,
    )
    retry_config = RetryConfig(base_delay=0.4, jitter=0.1)

    _BOT_POLICY_MAP: dict[str, ChatPolicy] = {
        "deny": ChatPolicy.DENY,
        "mention_only": ChatPolicy.MENTION_ONLY,
        "allow": ChatPolicy.ALLOW,
    }

    _DEFAULT_COMMANDS = (
        BotCommand(command="agent", description="Switch active agent"),
    )

    @classmethod
    def from_credentials(cls, creds: dict[str, str]) -> Self:
        from app.channels.core.credentials import parse_bool

        instance = cls(
            bot_token=creds.get("token", ""),
            commands=list(cls._DEFAULT_COMMANDS),
            webhook_url=creds.get("webhook_url") or None,
            auto_topic=parse_bool(creds.get("auto_topic", "false")),
        )
        instance._apply_bot_policy(creds.get("bot_policy", "deny"))
        instance._notifications_mode = parse_notification_mode(
            creds.get("notifications_mode", "important"),
        )
        return instance

    def __init__(
        self,
        bot_token: str,
        *,
        commands: list[BotCommand] | None = None,
        webhook_url: str | None = None,
        api_base: str | None = None,
        auto_topic: bool = False,
    ) -> None:
        super().__init__()
        self._token = bot_token
        self._client = TelegramClient(bot_token, api_base=api_base)
        self._poll_task: asyncio.Task[None] | None = None
        self._offset: int = 0
        self._bot_username: str | None = None
        self._tg_bot_id: int | None = None
        self._mg_buffers: dict[str, _MediaGroupBuffer] = {}
        self._mg_tasks: dict[str, asyncio.Task[None]] = {}
        self._background_tasks: set[asyncio.Task[None]] = set()
        self._commands = commands or []
        self._webhook_url = webhook_url.rstrip("/") if webhook_url else ""
        self._draft_counter = 0
        self._draft_available: bool | None = None
        self._active_drafts: dict[str, int] = {}
        self._rich_send_available: bool | None = None
        self._rich_draft_available: bool | None = None
        self._auto_topic = auto_topic
        self._notifications_mode = ChannelNotificationMode.IMPORTANT
        self._topic_locks: dict[str, asyncio.Lock] = {}
        self._topic_name_cache: dict[str, str] = {}
        self._user_topic_map: dict[str, int] = {}

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

    def _silent_notification_kwargs(self) -> dict[str, bool]:
        """Notification kwargs for progress/placeholder paths (silent in IMPORTANT mode)."""
        return notification_kwargs(self._notifications_mode, None)

    def _outbound_notification_kwargs(self, msg: OutboundMessage) -> dict[str, bool]:
        """Notification kwargs for final outbound replies."""
        return notification_kwargs(self._notifications_mode, msg)

    @property
    def is_webhook_mode(self) -> bool:
        """True when configured to receive updates via Webhook instead of Long Polling."""
        return bool(self._webhook_url)

    def _redact(self, text: str) -> str:
        """Strip bot token from text to prevent credential leakage in logs."""
        return text.replace(self._token, "bot<REDACTED>") if self._token else text

    @property
    def webhook_secret(self) -> str:
        """Deterministic secret_token derived from bot_token for webhook verification."""
        import hashlib

        return hashlib.sha256(self._token.encode()).hexdigest()[:32]

    def should_retry(self, exc: BaseException) -> bool:
        if isinstance(exc, TelegramApiError):
            if exc.error_code in (401, 403):
                return False
            if exc.error_code == 429:
                return True
        return super().should_retry(exc)

    def extract_retry_after(self, exc: BaseException) -> float | None:
        if isinstance(exc, TelegramApiError):
            ra = exc.parameters.get("retry_after")
            if isinstance(ra, (int, float)):
                return float(ra)
        return super().extract_retry_after(exc)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start in Webhook or Long Polling mode depending on configuration."""
        if not self._token:
            logger.info("Telegram bot token not configured; channel idle")
            return
        try:
            me = await self._client.get_me()
            self._bot_username = str(me.get("username", ""))
            self._tg_bot_id = me.get("id")
            self._bot_id = str(self._tg_bot_id) if self._tg_bot_id else ""
            logger.warning(
                "TelegramChannel: verified bot @%s (id=%s)",
                self._bot_username,
                self._tg_bot_id,
            )
        except Exception as exc:
            logger.warning("TelegramChannel: token verification failed: %s", self._redact(str(exc)))
            self._status = ChannelStatus.ERROR
            return

        await self._register_commands()
        self._status = ChannelStatus.RUNNING
        self._set_connected(True)

        if self.is_webhook_mode:
            try:
                await self._setup_webhook()
            except Exception as exc:
                logger.warning("TelegramChannel: setWebhook failed: %s", self._redact(str(exc)))
                self._status = ChannelStatus.DEGRADED
        else:
            await self._cleanup_webhook()
            self._poll_task = asyncio.create_task(self._poll_loop())
            logger.warning("TelegramChannel: polling started")

    async def stop(self) -> None:
        """Stop the channel, flush pending media groups, and clean up resources."""
        self._set_connected(False)
        self._status = ChannelStatus.STOPPED

        for draft_key, draft_id in list(self._active_drafts.items()):
            parts = draft_key.split(":draft:", 1)
            chat_id = parts[0] if len(parts) == 2 else ""
            if chat_id:
                try:
                    await self._client.send_message_draft(chat_id, draft_id, "")
                except Exception:
                    logger.debug("TelegramChannel: failed to clear draft %d on stop", draft_id)
        self._active_drafts.clear()

        pending = list(self._mg_buffers.values())
        for task in self._mg_tasks.values():
            task.cancel()
        self._mg_tasks.clear()
        self._mg_buffers.clear()

        for buf in pending:
            if buf.messages:
                await self._emit_inbound(self._merge_group(buf.messages))

        if self._poll_task:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
            self._poll_task = None

        if self.is_webhook_mode:
            await self._cleanup_webhook()

        if self._commands:
            await self._client.delete_my_commands()

        await self._client.close()
        logger.info("TelegramChannel: stopped")

    async def health_check(self) -> bool:
        """Verify connectivity via Telegram ``getMe`` API."""
        if self._status not in (ChannelStatus.RUNNING, ChannelStatus.DEGRADED):
            return False
        try:
            ok = await self._client.verify_token()
            if ok:
                self.health.record_success()
            else:
                self.health.record_failure("Token verification failed")
            return ok
        except Exception as exc:
            self.health.record_failure(self._redact(str(exc)))
            return False

    async def start_typing(self, chat_id: str) -> None:
        """Show 'typing...' indicator via sendChatAction."""
        await self._client.send_chat_action(chat_id, "typing")

    # ------------------------------------------------------------------
    # Outbound messaging
    # ------------------------------------------------------------------

    async def send(self, msg: OutboundMessage) -> str | None:
        """Send media attachments then text chunks via Telegram Bot API.

        When Bot API 10.1 Rich Messages are available, sends raw Markdown via
        ``sendRichMessage`` for native tables/math/headings rendering. Falls back
        transparently to the HTML path on capability or parse errors.
        """
        chat_id = msg.recipient_id
        if not chat_id:
            return None
        last_message_id: str | None = None
        notify_kwargs = self._outbound_notification_kwargs(msg)

        for attachment in msg.media:
            await send_media_attachment(
                self._client,
                chat_id,
                attachment,
                msg.reply_to_id,
                notification_kwargs=notify_kwargs,
            )

        if msg.content:
            reply_markup = build_inline_keyboard(msg)
            reply_to = int(msg.reply_to_id) if msg.reply_to_id else None
            thread_id = int(msg.thread_id) if msg.thread_id else None

            if self._rich_send_available is not False:
                mid = await self._try_send_rich(msg, chat_id, reply_to, thread_id, reply_markup, notify_kwargs)
                if mid is not None:
                    return mid

            chunks = render(msg, self.render_style)
            for i, chunk in enumerate(chunks):
                html_text = md_to_telegram_html(chunk)
                for part in split_message(html_text):
                    markup = reply_markup if (i == len(chunks) - 1 and reply_markup) else None
                    try:
                        result = await self._client.send_message(
                            chat_id,
                            part,
                            reply_to_message_id=reply_to,
                            message_thread_id=thread_id,
                            reply_markup=markup,
                            **notify_kwargs,
                        )
                        mid = result.get("message_id")
                        if mid is not None:
                            last_message_id = str(mid)
                        reply_to = None
                    except TelegramApiError as exc:
                        if exc.is_parse_error:
                            logger.warning("TelegramChannel: HTML parse failed, retrying as plain text")
                            result = await self._client.send_message(
                                chat_id,
                                part,
                                parse_mode="",
                                reply_to_message_id=reply_to,
                                message_thread_id=thread_id,
                                **notify_kwargs,
                            )
                            mid = result.get("message_id")
                            if mid is not None:
                                last_message_id = str(mid)
                            reply_to = None
                        else:
                            raise

        return last_message_id

    async def _try_send_rich(
        self,
        msg: OutboundMessage,
        chat_id: str,
        reply_to: int | None,
        thread_id: int | None,
        reply_markup: dict[str, object] | None,
        notify_kwargs: dict[str, bool],
    ) -> str | None:
        """Attempt to send via ``sendRichMessage``. Returns message_id or None to fall back."""
        from .html_converter import split_markdown_rich

        chunks = render(msg, self._rich_render_style)
        parts = split_markdown_rich(chunks[0]) if chunks else []
        if not parts:
            return None

        last_mid: str | None = None
        for i, part in enumerate(parts):
            markup = reply_markup if (i == len(parts) - 1 and reply_markup) else None
            try:
                result = await self._client.send_rich_message(
                    chat_id,
                    part,
                    reply_to_message_id=reply_to,
                    message_thread_id=thread_id,
                    reply_markup=markup,
                    **notify_kwargs,
                )
                self._rich_send_available = True
                mid = result.get("message_id")
                if mid is not None:
                    last_mid = str(mid)
                reply_to = None
            except TelegramApiError as exc:
                if exc.is_method_not_found:
                    self._rich_send_available = False
                    if last_mid is not None:
                        return last_mid
                    logger.info("TelegramChannel: sendRichMessage unavailable, using HTML mode")
                    return None
                if exc.error_code == 400:
                    if last_mid is not None:
                        logger.warning("TelegramChannel: Rich partial send stopped (%s)", exc.description)
                        return last_mid
                    logger.warning("TelegramChannel: sendRichMessage rejected (%s), falling back to HTML", exc.description)
                    return None
                raise

        for remaining_chunk in chunks[1:]:
            for part in split_markdown_rich(remaining_chunk):
                try:
                    result = await self._client.send_rich_message(
                        chat_id, part, message_thread_id=thread_id, **notify_kwargs,
                    )
                    mid = result.get("message_id")
                    if mid is not None:
                        last_mid = str(mid)
                except TelegramApiError:
                    break

        return last_mid

    def _allocate_draft_id(self) -> int:
        self._draft_counter = (self._draft_counter % 2_147_483_647) + 1
        return self._draft_counter

    def _draft_key(self, chat_id: str, message_id: str) -> str:
        return f"{chat_id}:{message_id}"

    async def _try_send_draft(self, chat_id: str, text: str, *, thread_id: str | None = None) -> int | None:
        """Attempt to send a draft preview. Returns draft_id on success, None if unavailable.

        Tries Rich Message draft first (Bot API 10.1) for native formatting, then
        falls back to HTML sendMessageDraft, then returns None for edit-based streaming.
        """
        tid = int(thread_id) if thread_id else None
        silent = self._silent_notification_kwargs()
        draft_id = self._allocate_draft_id()

        if self._rich_draft_available is not False:
            try:
                await self._client.send_rich_message_draft(
                    chat_id, draft_id, text, message_thread_id=tid,
                )
                self._rich_draft_available = True
                return draft_id
            except TelegramApiError as exc:
                if exc.is_method_not_found:
                    self._rich_draft_available = False
                    logger.info("TelegramChannel: sendRichMessageDraft unavailable")
                elif "can't be used" in exc.description.lower() or "can be used only" in exc.description.lower():
                    pass
                elif exc.error_code >= 500:
                    raise
                else:
                    self._rich_draft_available = False

        if self._draft_available is False:
            return None
        try:
            await self._client.send_message_draft(
                chat_id,
                draft_id,
                md_to_telegram_html(text),
                message_thread_id=tid,
                **silent,
            )
            self._draft_available = True
            return draft_id
        except TelegramApiError as exc:
            desc = exc.description.lower()
            if "unknown method" in desc or "not found" in desc or "not available" in desc or "not supported" in desc:
                self._draft_available = False
                logger.info("TelegramChannel: sendMessageDraft unavailable, using edit mode")
                return None
            if "can't be used" in desc or "can be used only" in desc:
                return None
            raise

    async def send_placeholder(self, chat_id: str, text: str, *, thread_id: str | None = None) -> str | None:
        """Send a placeholder via draft preview (DM) or regular message (fallback).

        When sendMessageDraft is available, the placeholder appears as a
        typing-style draft in the recipient's input area -- no push
        notification, no message flicker. On API unavailability or group
        chats, falls back to a regular message for editing.
        """
        silent = self._silent_notification_kwargs()
        draft_id = await self._try_send_draft(chat_id, text, thread_id=thread_id)
        if draft_id is not None:
            placeholder_id = f"draft:{draft_id}"
            self._active_drafts[self._draft_key(chat_id, placeholder_id)] = draft_id
            return placeholder_id

        try:
            tid = int(thread_id) if thread_id else None
            result = await self._client.send_message(
                chat_id,
                md_to_telegram_html(text),
                message_thread_id=tid,
                **silent,
            )
            return str(result.get("message_id", ""))
        except TelegramApiError as exc:
            if exc.is_parse_error:
                result = await self._client.send_message(
                    chat_id,
                    text,
                    parse_mode="",
                    message_thread_id=int(thread_id) if thread_id else None,
                    **silent,
                )
                return str(result.get("message_id", ""))
            logger.warning("TelegramChannel: placeholder failed: %s", exc)
            return None

    def _is_draft_id(self, message_id: str) -> bool:
        return message_id.startswith("draft:")

    async def edit_message(self, chat_id: str, message_id: str, text: str) -> None:
        """Edit a message or update a draft preview.

        Draft updates are suppressed until text exceeds ``_MIN_DRAFT_CHARS``
        to avoid rapid visual flicker during the first few streaming tokens.
        Rich Message draft path is used when ``_rich_draft_available`` is True.
        """
        draft_key = self._draft_key(chat_id, message_id)
        draft_id = self._active_drafts.get(draft_key)
        silent = self._silent_notification_kwargs()

        if draft_id is not None:
            if len(text) < _MIN_DRAFT_CHARS:
                return
            if self._rich_draft_available is True:
                try:
                    await self._client.send_rich_message_draft(chat_id, draft_id, text)
                    return
                except TelegramApiError:
                    pass
            try:
                await self._client.send_message_draft(
                    chat_id,
                    draft_id,
                    md_to_telegram_html(text),
                    **silent,
                )
                return
            except TelegramApiError:
                pass

        if self._is_draft_id(message_id):
            return

        if self._rich_send_available is True:
            try:
                await self._client.edit_message_text(
                    chat_id,
                    int(message_id),
                    text,
                    rich_message={"markdown": text},
                    **silent,
                )
                return
            except TelegramApiError as exc:
                if exc.is_not_modified:
                    return
                if exc.error_code != 400:
                    logger.warning("TelegramChannel: rich edit failed: %s", exc)

        try:
            await self._client.edit_message_text(
                chat_id,
                int(message_id),
                md_to_telegram_html(text),
                **silent,
            )
        except TelegramApiError as exc:
            if exc.is_not_modified:
                return
            if exc.is_parse_error:
                try:
                    await self._client.edit_message_text(
                        chat_id,
                        int(message_id),
                        text,
                        parse_mode="",
                        **silent,
                    )
                except TelegramApiError as inner:
                    if not inner.is_not_modified:
                        logger.warning("TelegramChannel: edit failed: %s", inner)
                return
            logger.warning("TelegramChannel: edit failed: %s", exc)

    async def edit_placeholder_message(
        self,
        chat_id: str,
        message_id: str,
        msg: OutboundMessage,
    ) -> None:
        """Finalize a placeholder: materialize draft into a permanent message, or edit in-place.

        When Rich Messages are available, the final message is sent/edited with
        native formatting; falls back to HTML then plain text on any failure.
        """
        notify_kwargs = self._outbound_notification_kwargs(msg)
        silent = self._silent_notification_kwargs()
        reply_markup = build_inline_keyboard(msg)

        draft_key = self._draft_key(chat_id, message_id)
        draft_id = self._active_drafts.pop(draft_key, None)
        if draft_id is not None:
            try:
                await self._client.send_message_draft(chat_id, draft_id, "", **silent)
            except TelegramApiError:
                pass

            thread_id = int(msg.thread_id) if msg.thread_id else None

            if self._rich_send_available is not False:
                rich_chunks = render(msg, self._rich_render_style)
                if rich_chunks:
                    try:
                        await self._client.send_rich_message(
                            chat_id,
                            rich_chunks[0],
                            message_thread_id=thread_id,
                            reply_markup=reply_markup,
                            **notify_kwargs,
                        )
                        self._rich_send_available = True
                        return
                    except TelegramApiError as exc:
                        if exc.is_method_not_found:
                            self._rich_send_available = False
                        elif exc.error_code >= 500:
                            raise

            chunks = render(msg, self.render_style)
            html_text = md_to_telegram_html(chunks[0]) if chunks else ""
            try:
                await self._client.send_message(
                    chat_id,
                    html_text,
                    message_thread_id=thread_id,
                    reply_markup=reply_markup,
                    **notify_kwargs,
                )
            except TelegramApiError as exc:
                if exc.is_parse_error:
                    await self._client.send_message(
                        chat_id,
                        chunks[0] if chunks else "",
                        parse_mode="",
                        message_thread_id=thread_id,
                        reply_markup=reply_markup,
                        **notify_kwargs,
                    )
                else:
                    logger.warning("TelegramChannel: draft materialize failed: %s", exc)
            return

        if self._rich_send_available is True:
            rich_chunks = render(msg, self._rich_render_style)
            if rich_chunks:
                try:
                    await self._client.edit_message_text(
                        chat_id,
                        int(message_id),
                        rich_chunks[0],
                        rich_message={"markdown": rich_chunks[0]},
                        reply_markup=reply_markup,
                        **notify_kwargs,
                    )
                    return
                except TelegramApiError as exc:
                    if exc.is_not_modified:
                        return
                    if exc.error_code >= 500:
                        raise

        chunks = render(msg, self.render_style)
        html_text = md_to_telegram_html(chunks[0]) if chunks else ""
        try:
            await self._client.edit_message_text(
                chat_id,
                int(message_id),
                html_text,
                reply_markup=reply_markup,
                **notify_kwargs,
            )
        except TelegramApiError as exc:
            if exc.is_not_modified:
                return
            if exc.is_parse_error:
                try:
                    await self._client.edit_message_text(
                        chat_id,
                        int(message_id),
                        chunks[0] if chunks else "",
                        parse_mode="",
                        reply_markup=reply_markup,
                        **notify_kwargs,
                    )
                except TelegramApiError as inner:
                    if not inner.is_not_modified:
                        logger.warning("TelegramChannel: edit_placeholder failed: %s", inner)
                return
            logger.warning("TelegramChannel: edit_placeholder failed: %s", exc)

    async def delete_message(self, chat_id: str, message_id: str) -> None:
        """Delete a message via deleteMessage. Draft-only placeholders are silently skipped."""
        if self._is_draft_id(message_id):
            draft_key = self._draft_key(chat_id, message_id)
            draft_id = self._active_drafts.pop(draft_key, None)
            if draft_id is not None:
                try:
                    silent = self._silent_notification_kwargs()
                    await self._client.send_message_draft(chat_id, draft_id, "", **silent)
                except TelegramApiError:
                    pass
            return
        await self._client.delete_message(chat_id, int(message_id))

    async def react_to_message(self, chat_id: str, message_id: str, emoji: str) -> None:
        """Add or remove a reaction via setMessageReaction (Bot API 7.2+)."""
        reaction = [{"type": "emoji", "emoji": emoji}] if emoji else []
        await self._client.set_message_reaction(chat_id, int(message_id), reaction)

    async def pin_message(self, chat_id: str, message_id: str) -> None:
        """Pin a message in a chat."""
        try:
            await self._client.pin_chat_message(chat_id, int(message_id))
        except TelegramApiError as exc:
            logger.warning("TelegramChannel: pin failed: %s", exc)

    # ------------------------------------------------------------------
    # Forum Topic management
    # ------------------------------------------------------------------

    async def create_topic(
        self,
        chat_id: str,
        name: str,
        *,
        icon_color: int | None = None,
        icon_custom_emoji_id: str | None = None,
    ) -> int | None:
        """Create a Forum topic. Returns the message_thread_id or None on failure."""
        try:
            result = await self._client.create_forum_topic(
                chat_id,
                name,
                icon_color=icon_color,
                icon_custom_emoji_id=icon_custom_emoji_id,
            )
            thread_id = result.get("message_thread_id")
            if isinstance(thread_id, int):
                self._topic_name_cache[f"{chat_id}:{thread_id}"] = name
                return thread_id
            return None
        except TelegramApiError as exc:
            logger.warning("TelegramChannel: create_topic failed: %s", exc)
            return None

    async def rename_topic(self, chat_id: str, message_thread_id: int, name: str) -> bool:
        """Rename a Forum topic."""
        try:
            result = await self._client.edit_forum_topic(chat_id, message_thread_id, name=name)
            if result:
                self._topic_name_cache[f"{chat_id}:{message_thread_id}"] = name
            return result
        except TelegramApiError as exc:
            logger.warning("TelegramChannel: rename_topic failed: %s", exc)
            return False

    async def close_topic(self, chat_id: str, message_thread_id: int) -> bool:
        """Close a Forum topic (stops new messages from non-admins)."""
        try:
            return await self._client.close_forum_topic(chat_id, message_thread_id)
        except TelegramApiError as exc:
            logger.warning("TelegramChannel: close_topic failed: %s", exc)
            return False

    async def reopen_topic(self, chat_id: str, message_thread_id: int) -> bool:
        """Reopen a previously closed Forum topic."""
        try:
            return await self._client.reopen_forum_topic(chat_id, message_thread_id)
        except TelegramApiError as exc:
            logger.warning("TelegramChannel: reopen_topic failed: %s", exc)
            return False

    async def ensure_topic_for_user(
        self,
        chat_id: str,
        sender_name: str,
        sender_id: str,
    ) -> int | None:
        """Auto-create a Forum topic for a user, or reuse an existing one.

        Maintains a sender->topic mapping to prevent duplicate topic creation.
        Uses per-user locking to prevent concurrent race conditions.
        Returns the message_thread_id of the existing or newly created topic,
        or None if auto_topic is disabled or creation failed.
        """
        if not self._auto_topic:
            return None

        map_key = f"{chat_id}:{sender_id}"
        existing = self._user_topic_map.get(map_key)
        if existing is not None:
            return existing

        if map_key not in self._topic_locks:
            self._topic_locks[map_key] = asyncio.Lock()

        async with self._topic_locks[map_key]:
            existing = self._user_topic_map.get(map_key)
            if existing is not None:
                return existing

            thread_id = await self.create_topic(chat_id, sender_name or f"User {sender_id}")
            if thread_id is not None:
                self._user_topic_map[map_key] = thread_id
            return thread_id

    async def sync_topic_name(
        self,
        chat_id: str,
        message_thread_id: int,
        current_name: str,
    ) -> None:
        """Sync the Forum topic name if the user's display name has changed.

        Only calls editForumTopic when the cached name differs from the current
        display name to avoid unnecessary API calls.
        """
        if not self._auto_topic:
            return

        cache_key = f"{chat_id}:{message_thread_id}"
        cached = self._topic_name_cache.get(cache_key)
        if cached == current_name:
            return

        if await self.rename_topic(chat_id, message_thread_id, current_name):
            logger.info(
                "TelegramChannel: synced topic name %s -> %s in chat %s",
                cached,
                current_name,
                chat_id,
            )

    def collect_issues(self) -> list[ChannelIssue]:
        """Diagnostics for Telegram channel configuration and runtime health."""
        issues: list[ChannelIssue] = []
        if not self._token:
            issues.append(
                ChannelIssue(
                    kind=IssueKind.CONFIG,
                    severity=IssueSeverity.ERROR,
                    message="No bot token configured.",
                    fix="Set TELEGRAM_BOT_TOKEN environment variable or configure in Settings → Channels → Telegram.",
                )
            )
            return issues
        if self._webhook_url and not self._webhook_url.startswith("https://"):
            issues.append(
                ChannelIssue(
                    kind=IssueKind.CONFIG,
                    severity=IssueSeverity.WARNING,
                    message="Webhook URL must use HTTPS. Telegram rejects non-HTTPS URLs.",
                    fix="Update TELEGRAM_WEBHOOK_URL to use https://.",
                )
            )
        if self._status == ChannelStatus.DEGRADED:
            issues.append(
                ChannelIssue(
                    kind=IssueKind.CONFIG,
                    severity=IssueSeverity.WARNING,
                    message="Webhook setup failed. Channel running in degraded mode.",
                    fix="Check TELEGRAM_WEBHOOK_URL is reachable and retry, or switch to polling mode.",
                )
            )
        if self.health.last_error:
            issues.append(
                ChannelIssue(
                    kind=IssueKind.RUNTIME,
                    severity=IssueSeverity.ERROR,
                    message=self._redact(self.health.last_error),
                )
            )
        return issues

    async def verify(self, request: Request, body: bytes) -> None:
        """SignatureVerifier Protocol: validate X-Telegram-Bot-Api-Secret-Token header."""
        actual = request.headers.get("x-telegram-bot-api-secret-token", "")
        if not hmac.compare_digest(actual, self.webhook_secret):
            raise WebhookResponseError(
                status_code=403,
                error_type="signature-invalid",
                title="Invalid Signature",
                detail="Telegram webhook secret token verification failed",
                trace_id=request.state._webhook_trace_id if hasattr(request.state, "_webhook_trace_id") else "",
            )

    async def handle_webhook_update(self, update: dict[str, object]) -> None:
        """Process a Telegram webhook update (called by FastAPI endpoint)."""
        msg = self._parse_update(update)
        if msg:
            msg = await self._pre_emit_hook(msg)
            if msg:
                await self._buffer_or_emit(msg, update)

    async def _pre_emit_hook(self, msg: InboundMessage) -> InboundMessage | None:
        """Intercept bot commands and apply auto-topic before emitting."""
        intercepted = await self._handle_agent_command(msg)
        if intercepted is None:
            return None
        return await self._apply_auto_topic(intercepted)

    async def _handle_agent_command(self, msg: InboundMessage) -> InboundMessage | None:
        """Intercept /agent command and ag: callback for inline agent switching.

        Returns None when the message was fully handled (suppressed from agent routing).
        """
        prefix = msg.metadata.get("callback_prefix")

        if prefix == "ag":
            return await self._handle_agent_callback(msg)

        content = (msg.content or "").strip().lower()
        bot_suffix = f"/agent@{self._bot_username}".lower() if self._bot_username else ""
        if content == "/agent" or (bot_suffix and content == bot_suffix):
            try:
                await self._send_agent_picker(msg)
            except Exception as exc:
                logger.warning("TelegramChannel: /agent picker failed: %s", exc)
            return None

        return msg

    async def _send_agent_picker(self, msg: InboundMessage) -> None:
        """Query available agents and send an inline keyboard picker."""
        from app.core.channel_bridge.topic_config import SqlTopicManager
        from app.services.agent.agent_service import AgentService

        agents, _ = await AgentService.get_agent_list(page=1, page_size=50)
        chat_id = msg.chat_id or msg.sender_id
        if not chat_id:
            return

        if not agents:
            await self._client.send_message(
                chat_id,
                get_text(msg, "agent_picker_no_agents"),
                message_thread_id=int(msg.thread_id) if msg.thread_id else None,
            )
            return

        topic_mgr = SqlTopicManager()
        bound_agent_id: str | None = None
        if msg.thread_id:
            ctx = await topic_mgr.resolve_topic(msg.channel, chat_id, msg.thread_id)
            if ctx and ctx.agent_id:
                bound_agent_id = ctx.agent_id
        if not bound_agent_id:
            ctx = await topic_mgr.resolve_topic(msg.channel, chat_id, None)
            if ctx and ctx.agent_id:
                bound_agent_id = ctx.agent_id

        keyboard_rows: list[list[dict[str, str]]] = []
        for agent in agents:
            label = agent.display_name or agent.id
            if agent.id == bound_agent_id:
                label = f"✅ {label}"
            keyboard_rows.append([{"text": label, "callback_data": f"ag:{agent.id}"}])

        reply_markup = {"inline_keyboard": keyboard_rows}
        await self._client.send_message(
            chat_id,
            get_text(msg, "agent_picker_select"),
            message_thread_id=int(msg.thread_id) if msg.thread_id else None,
            reply_markup=reply_markup,
        )

    async def _handle_agent_callback(self, msg: InboundMessage) -> InboundMessage | None:
        """Update picker message with confirmation, then convert to /bind."""
        agent_id = (msg.content or "").strip()
        if not agent_id:
            return msg

        origin_msg_id = msg.metadata.get("origin_message_id")
        chat_id = msg.chat_id or msg.sender_id
        if origin_msg_id and chat_id:
            try:
                from app.services.agent.agent_service import AgentService

                agent = await AgentService.get_agent_by_id(agent_id)
                name = agent.display_name if agent else agent_id
                switched_text = get_text(msg, "agent_picker_switched", name=name)
                await self._client.edit_message_text(
                    chat_id,
                    int(origin_msg_id),
                    f"<b>{switched_text}</b>",
                    reply_markup={"inline_keyboard": []},
                )
            except Exception as exc:
                logger.debug("TelegramChannel: edit picker failed: %s", exc)

        return dataclasses.replace(msg, content=f"/bind {agent_id}")

    async def _apply_auto_topic(self, msg: InboundMessage) -> InboundMessage:
        """Auto-create a Forum topic and sync name for inbound messages.

        Only triggers when auto_topic is enabled, the chat is a Forum supergroup,
        and the message has no existing thread_id. Also syncs topic name on
        subsequent messages if the user's display name has changed.
        """
        if not self._auto_topic:
            return msg

        metadata = msg.metadata or {}
        is_forum = metadata.get("is_forum", False)
        if not is_forum or not msg.is_group:
            return msg

        if msg.thread_id and msg.sender_id:
            map_key = f"{msg.chat_id}:{msg.sender_id}"
            self._user_topic_map[map_key] = int(msg.thread_id)

            if msg.sender_name:
                task = asyncio.create_task(self.sync_topic_name(msg.chat_id, int(msg.thread_id), msg.sender_name))
                self._background_tasks.add(task)
                task.add_done_callback(self._background_tasks.discard)
            return msg

        if not msg.thread_id and msg.sender_id:
            thread_id = await self.ensure_topic_for_user(
                msg.chat_id,
                msg.sender_name or "",
                msg.sender_id,
            )
            if thread_id is not None:
                return InboundMessage(
                    channel=msg.channel,
                    sender_id=msg.sender_id,
                    content=msg.content,
                    sent_at=msg.sent_at,
                    sent_timezone=msg.sent_timezone,
                    chat_id=msg.chat_id,
                    sender_name=msg.sender_name,
                    is_group=msg.is_group,
                    is_bot=msg.is_bot,
                    mentioned=msg.mentioned,
                    media=msg.media,
                    reply_to_id=msg.reply_to_id,
                    reply_to=msg.reply_to,
                    thread_id=str(thread_id),
                    metadata=metadata,
                    message_id=msg.message_id,
                )

        return msg

    async def download_voice_message(self, file_id: str) -> Path | None:
        """Download a Telegram voice/audio file via getFile API to a local temp path."""
        return await self._client.download_voice(file_id)

    async def download_video_file(self, file_id: str) -> Path | None:
        """Download a Telegram video/video_note via getFile API to a local temp path."""
        return await self._client.download_video(file_id)

    # ------------------------------------------------------------------
    # Internal: commands, webhook
    # ------------------------------------------------------------------

    async def _register_commands(self) -> None:
        """Register bot commands via setMyCommands."""
        if not self._commands:
            await self._client.delete_my_commands()
            return
        try:
            await self._client.set_my_commands(
                [{"command": cmd.command, "description": cmd.description} for cmd in self._commands]
            )
            logger.warning("TelegramChannel: registered %d commands", len(self._commands))
        except TelegramApiError as exc:
            logger.warning("TelegramChannel: setMyCommands failed: %s", exc)

    async def _setup_webhook(self) -> None:
        """Register the webhook URL with Telegram via setWebhook API."""
        await self._client.set_webhook(
            self._webhook_url,
            secret_token=self.webhook_secret,
            allowed_updates=_ALLOWED_UPDATES,
        )
        logger.warning("TelegramChannel: webhook registered at %s", self._webhook_url)

    async def _cleanup_webhook(self) -> None:
        """Remove any registered webhook. Best-effort."""
        try:
            await self._client.delete_webhook()
        except Exception as exc:
            logger.debug("TelegramChannel: deleteWebhook failed: %s", self._redact(str(exc)))

    def register_routes(self, registrar: object) -> None:
        """Register custom HTTP routes for Telegram webhook.

        Registers POST /webhook endpoint for receiving Telegram Bot API updates.
        Applies WebhookSecurityMiddleware for signature verification and rate limiting.

        Args:
            registrar: RouteRegistrar Protocol implementation (e.g., FastAPIRouteRegistrar)
        """
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
            """Handle Telegram webhook updates."""
            import json

            try:
                ctx = await middleware.process_request(request, "telegram")

                if ctx.parsed_data is None:

                    class _ErrorResponse:
                        status_code = 400
                        headers = {}
                        body = b'{"ok": false, "error": "Invalid JSON"}'

                    return _ErrorResponse()

                await self.handle_webhook_update(ctx.parsed_data)

            except WebhookResponseError as e:

                class _WebhookErrorResponse:
                    status_code = e.status_code
                    headers = {}
                    body = json.dumps(e.to_dict()).encode("utf-8")

                return _WebhookErrorResponse()
            except Exception as e:
                logger.warning("Telegram webhook error: %s", e, exc_info=True)

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
                description="Receive Telegram Bot API webhook updates",
                requires_auth=False,
                # rate_limit_policy=RateLimitConfig(max_requests=60, window_seconds=60),
            ),
        )
