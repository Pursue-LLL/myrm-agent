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
- telegram.inbound::TelegramInboundMixin (POS: Telegram inbound message parsing and media-group aggregation mixin.)
- telegram.outbound::TelegramOutboundMixin (POS: Telegram outbound messaging mixin.)
- telegram.topics::TelegramTopicsMixin (POS: Telegram Forum Topic lifecycle helpers.)
- telegram.hooks::TelegramHooksMixin (POS: Telegram pre-emit hook mixin.)
- telegram.webhook::TelegramWebhookMixin (POS: Telegram webhook verification and route registration.)

[OUTPUT]
- TelegramChannel: Telegram Bot bidirectional Channel (polling + webhook)

[POS]
Telegram Bot channel implementation. Composes inbound/outbound/topics/hooks/webhook mixins
for DM and group chat, media group debounce, webhook/polling dual mode, inline keyboard
rendering, Markdown -> HTML conversion, message splitting, command registration, /agent
inline picker (agent switching via Inline Keyboard), diagnostics,
and Forum Topic management (create/rename/close/reopen, auto-topic, name sync).
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Self

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
from app.channels.types import (
    ChannelCapabilities,
    ChannelIssue,
    ChannelStatus,
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
from .helpers import (
    MAX_TEXT_LENGTH,
    BotCommand,
    _MediaGroupBuffer,
)
from .hooks import TelegramHooksMixin
from .inbound import TelegramInboundMixin
from .outbound import TelegramOutboundMixin
from .topics import TelegramTopicsMixin
from .webhook import TelegramWebhookMixin

logger = logging.getLogger(__name__)

_RICH_MAX_TEXT_LENGTH = 32000  # practical limit below 32768 to leave headroom


class TelegramChannel(
    TelegramInboundMixin,
    TelegramOutboundMixin,
    TelegramTopicsMixin,
    TelegramHooksMixin,
    TelegramWebhookMixin,
    BaseChannel,
):
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
        typing_keepalive_interval=4.0,
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
        BotCommand(command="memory", description="Review pending memory writes"),
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

    async def download_voice_message(self, file_id: str) -> Path | None:
        """Download a Telegram voice/audio file via getFile API to a local temp path."""
        return await self._client.download_voice(file_id)

    async def download_video_file(self, file_id: str) -> Path | None:
        """Download a Telegram video/video_note via getFile API to a local temp path."""
        return await self._client.download_video(file_id)
