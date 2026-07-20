"""WeChat iLink channel — personal account via iLink Bot protocol.

Inbound: Long-polling getupdates → parse ILinkMessage → _emit_inbound
  - Text, Image (multimodal), Voice (STT via SILK→WAV), File, Video
  - Auto-reconnect on session expiration with exponential backoff
Outbound: sendmessage with text/media items, CDN upload with AES encryption

[INPUT]
- channels.core.base::BaseChannel (POS: Provides FileOperationObserver.)
- providers._ilink.client::ILinkClient (POS: iLink Bot protocol HTTP client. Single-instance httpx connection reuse with unified exception mapping.)
- providers._ilink.media::process_inbound_item, (POS: iLink media processing utility functions. Inbound parsing and outbound upload, zero state dependencies.)
- providers._ilink.types::data (POS: Pure data type definitions and serialization utilities for the iLink Bot protocol.)

[OUTPUT]
- WeChatILinkChannel: WeChat personal account bidirectional Channel (iLink long-polling)

[POS]
WeChat personal account channel implementation. Sends/receives messages via iLink Bot protocol.
Supports text, image, voice (STT), file, video, and typing indicator.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator
from pathlib import Path

from myrm_agent_harness.runtime.lazy_deps import feature_missing

from app.channels.core.base import BaseChannel
from app.channels.core.credentials import credential_field, credential_spec
from app.channels.core.exceptions import ChannelAuthError
from app.channels.helpers import QRCodeLoginHelper
from app.channels.protocols import LoginEvent, LoginMethod
from app.channels.providers._ilink.client import ILinkClient
from app.channels.providers._ilink.media import (
    cleanup_temp_dir,
    prepare_outbound_media,
    process_inbound_item,
)
from app.channels.providers._ilink.types import (
    ILinkCredentials,
    ILinkMessage,
    ItemType,
    MessageItem,
    MessageType,
    TextItem,
    TypingStatus,
)
from app.channels.rendering.renderer import render
from app.channels.types import (
    ChannelCapabilities,
    ChannelIssue,
    ChannelStatus,
    InboundMessage,
    IssueKind,
    IssueSeverity,
    MediaAttachment,
    OutboundMessage,
    RenderStyle,
    StartMode,
)

logger = logging.getLogger(__name__)

_WECHAT_SILK_FEATURE = "platform.wechat-silk"
_WECHAT_SILK_INSTALL = "uv sync --extra wechat-silk"

_MAX_TEXT_LENGTH = 4096
_MAX_CONSECUTIVE_FAILURES = 5
_INITIAL_BACKOFF = 2.0
_MAX_BACKOFF = 30.0

_TYPING_TICKET_TTL = 540.0  # iLink platform TTL is 600s; 60s buffer for proactive refresh


class WeChatILinkChannel(BaseChannel):
    """WeChat personal account channel using iLink Bot protocol.

    Inbound: Long-polling for messages (text, image, voice, file, video)
    Outbound: Send text and media via iLink API with CDN encryption
    """

    name = "wechat"
    start_mode = StartMode.ON_DEMAND
    credential_spec = credential_spec(
        "wechatCredentials",
        bot_token=credential_field("botToken", "WECHAT_BOT_TOKEN"),
        ilink_bot_id=credential_field("ilinkBotId", "WECHAT_ILINK_BOT_ID"),
        base_url=credential_field("baseUrl", "WECHAT_BASE_URL", "https://ilinkai.weixin.qq.com"),
        ilink_user_id=credential_field("ilinkUserId", "WECHAT_ILINK_USER_ID"),
    )
    capabilities = ChannelCapabilities(
        text=True,
        markdown=False,
        media=True,
        voice_message=True,
        file_upload=True,
        typing_indicator=True,
        typing_keepalive_interval=5.0,
        max_text_length=_MAX_TEXT_LENGTH,
    )
    render_style = RenderStyle(
        format="plaintext",
        max_text_length=_MAX_TEXT_LENGTH,
        use_emoji=True,
    )
    supported_login_methods = [LoginMethod.QR_CODE]

    def should_auto_start(self) -> bool:
        """Auto-start only when persisted bot_token exists (QR login was completed before)."""
        return bool(self._client.credentials and self._client.credentials.bot_token)

    def __init__(
        self,
        bot_token: str = "",
        ilink_bot_id: str = "",
        base_url: str = "",
        ilink_user_id: str = "",
    ) -> None:
        super().__init__()

        creds: ILinkCredentials | None = None
        if bot_token and ilink_bot_id:
            creds = ILinkCredentials(
                bot_token=bot_token,
                ilink_bot_id=ilink_bot_id,
                base_url=base_url or "https://ilinkai.weixin.qq.com",
                ilink_user_id=ilink_user_id or None,
            )

        self._client = ILinkClient(creds)
        self._poll_task: asyncio.Task[None] | None = None
        self._get_updates_buf = ""
        self._context_tokens: dict[str, str] = {}
        self._typing_tickets: dict[str, tuple[str, float]] = {}
        self._temp_files: set[Path] = set()
        self._login_helper: QRCodeLoginHelper | None = None

    # ── Poll state (readable/writable for external persistence) ───────

    @property
    def poll_state(self) -> str:
        """Current long-polling cursor. Set before start() to resume."""
        return self._get_updates_buf

    @poll_state.setter
    def poll_state(self, value: str) -> None:
        self._get_updates_buf = value

    # ── Async Login (AsyncLoginProtocol) ──────────────────────────────

    async def start_login(
        self,
        method: object,
        *,
        timeout: float = 300.0,
        callback_url: str | None = None,
    ) -> AsyncIterator[LoginEvent]:
        """Start async QR code login flow.

        Implements AsyncLoginProtocol for WeChat iLink QR authentication.

        Args:
            method: LoginMethod.QR_CODE (only supported method)
            timeout: Maximum seconds to wait for QR scan
            callback_url: Not used (QR login does not require callback URL)

        Yields:
            LoginEvent: State change events

        Raises:
            ValueError: If method is not LoginMethod.QR_CODE
            ChannelAuthError: If QR fetch or polling fails
            TimeoutError: If login times out
        """
        if method != LoginMethod.QR_CODE:
            raise ValueError(f"Unsupported login method: {method}, expected QR_CODE")

        if self._client.http.is_closed:
            self._client = ILinkClient(self._client.credentials)

        self._login_helper = QRCodeLoginHelper(
            fetch_qr_fn=self._fetch_qr_code,
            poll_status_fn=self._poll_qr_status,
            max_refresh=3,
            qr_ttl=120.0,
            poll_interval=1.0,
        )

        async for event in self._login_helper.run(timeout, self.name):
            if event.credentials:
                creds = ILinkCredentials(
                    bot_token=event.credentials["bot_token"],
                    ilink_bot_id=event.credentials["ilink_bot_id"],
                    base_url=event.credentials.get("base_url", "https://ilinkai.weixin.qq.com"),
                    ilink_user_id=event.credentials.get("ilink_user_id"),
                )
                self._client = ILinkClient(creds)
                if self._status != ChannelStatus.RUNNING:
                    await self.start()
                logger.info("WeChatILinkChannel: QR login successful")

            yield event

    async def cancel_login(self) -> None:
        """Cancel current QR login flow."""
        if self._login_helper:
            self._login_helper.cancel()
        self._client._qr_code_cache = None
        logger.info("WeChatILinkChannel: QR login cancelled")

    async def _fetch_qr_code(self) -> tuple[str, bytes]:
        """Fetch QR code from iLink API.

        Returns:
            (qr_id, qr_image_bytes) where qr_id is the qrcode string
            and qr_image_bytes is the decoded PNG image.
        """
        import base64

        qr_id, qr_image_base64 = await self._client.fetch_qr_code()
        self._client._qr_code_cache = {"qr_id": qr_id, "qr_image_base64": qr_image_base64}
        qr_image_bytes = base64.b64decode(qr_image_base64)
        return qr_id, qr_image_bytes

    async def _poll_qr_status(self, qr_id: str) -> dict[str, str] | None:
        """Poll QR scan status.

        Args:
            qr_id: QR code ID from fetch

        Returns:
            Credentials dict if scanned, None if pending

        Raises:
            ChannelAuthError: If QR expired or polling failed
        """
        try:
            creds = await self._client.poll_qr_status(qr_id)
        except ChannelAuthError as exc:
            if "expired" in str(exc).lower():
                raise
            logger.error("WeChatILinkChannel: QR polling failed: %s", exc)
            raise

        if creds:
            return {
                "bot_token": creds.bot_token,
                "ilink_bot_id": creds.ilink_bot_id,
                "base_url": creds.base_url,
                "ilink_user_id": creds.ilink_user_id or "",
            }
        return None

    # ── Lifecycle ──────────────────────────────────────────────────────

    async def start(self) -> None:
        if not self._client.credentials:
            logger.info("WeChat iLink credentials not configured; channel idle")
            self._status = ChannelStatus.STOPPED
            return

        if self._poll_task and not self._poll_task.done():
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass

        if self._client.http.is_closed:
            self._client = ILinkClient(self._client.credentials)

        creds = self._client.credentials
        assert creds is not None
        self.health.record_success()
        self._status = ChannelStatus.RUNNING
        self._poll_task = asyncio.create_task(self._poll_loop())
        self._set_connected(True)
        logger.info("WeChatILinkChannel: polling started (bot_id=%s)", creds.ilink_bot_id)

    async def stop(self) -> None:
        self._set_connected(False)
        self._status = ChannelStatus.STOPPED

        if self._login_helper:
            await self.cancel_login()
            self._login_helper = None

        if self._poll_task:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
            self._poll_task = None

        for tmp_file in self._temp_files:
            tmp_file.unlink(missing_ok=True)
        self._temp_files.clear()
        cleanup_temp_dir()

        await self._client.close()
        logger.info("WeChatILinkChannel: stopped")

    async def health_check(self) -> bool:
        if self._status not in (ChannelStatus.RUNNING, ChannelStatus.DEGRADED):
            return False
        if not self._client.credentials:
            return False
        poll_alive = self._poll_task is not None and not self._poll_task.done()
        if not poll_alive:
            return False
        try:
            await self._client.get_config(
                ilink_user_id=self._client.credentials.ilink_bot_id,
                context_token=None,
            )
            return True
        except ChannelAuthError:
            return False
        except Exception:
            return poll_alive

    def collect_issues(self) -> list[ChannelIssue]:
        issues: list[ChannelIssue] = []
        if self._status == ChannelStatus.DISABLED:
            return issues
        if not self._client.credentials:
            issues.append(
                ChannelIssue(
                    kind=IssueKind.CONFIG,
                    severity=IssueSeverity.INFO,
                    message="WeChat not logged in.",
                    fix="Go to Settings → Channels → WeChat and scan QR code to login.",
                )
            )
            return issues
        poll_alive = self._poll_task is not None and not self._poll_task.done()
        if self.health.last_error and not poll_alive:
            issues.append(
                ChannelIssue(
                    kind=IssueKind.RUNTIME,
                    severity=IssueSeverity.ERROR,
                    message=self.health.last_error,
                )
            )
        if feature_missing(_WECHAT_SILK_FEATURE):
            issues.append(
                ChannelIssue(
                    kind=IssueKind.DEPENDENCY,
                    severity=IssueSeverity.WARNING,
                    message=(
                        "Voice SILK decoder (pilk, GPLv3) is not installed. "
                        "Voice messages without platform ASR text will be dropped."
                    ),
                    fix=_WECHAT_SILK_INSTALL,
                )
            )
        return issues

    def get_status_info(self) -> dict[str, object]:
        poll_alive = self._poll_task is not None and not self._poll_task.done()
        is_connected = (
            self._status in (ChannelStatus.RUNNING, ChannelStatus.DEGRADED) and bool(self._client.credentials) and poll_alive
        )
        info: dict[str, object] = {
            "connected": is_connected,
            "qr_code": self._client.qr_code_cache,
            "bot_id": (self._client.credentials.ilink_bot_id if self._client.credentials else None),
            "status": self._status.value,
        }
        if not is_connected and self.health.last_error:
            info["error"] = self.health.last_error
        return info

    # ── Outbound ───────────────────────────────────────────────────────

    async def send(self, msg: OutboundMessage) -> str | None:
        to_user_id = msg.recipient_id
        if not to_user_id:
            logger.warning("WeChatILinkChannel: no recipient_id, skipping")
            return None

        context_token = self._context_tokens.get(to_user_id)
        items: list[MessageItem] = []

        if msg.media:
            for attachment in msg.media:
                item = await prepare_outbound_media(
                    attachment,
                    to_user_id,
                    self._client.get_upload_url,
                    self._client.http,
                )
                if item:
                    items.append(item)

        if msg.content:
            chunks = render(msg, self.render_style)
            for chunk in chunks:
                items.append(MessageItem(type=ItemType.TEXT, text_item=TextItem(text=chunk)))

        if items:
            await self._client.send_message(to_user_id, items, context_token)
            logger.info("WeChatILinkChannel: sent to %s (items=%d)", to_user_id, len(items))

        return None

    async def _ensure_typing_ticket(self, chat_id: str) -> str | None:
        """Return a valid typing ticket, refreshing from getConfig if expired.

        iLink typing tickets have a 600s TTL.  We use a 540s buffer
        (_TYPING_TICKET_TTL) to refresh proactively before expiry.
        Timestamps use ``time.monotonic()`` for clock-drift safety.
        """
        entry = self._typing_tickets.get(chat_id)
        if entry:
            ticket, stored_at = entry
            if time.monotonic() - stored_at < _TYPING_TICKET_TTL:
                return ticket
            del self._typing_tickets[chat_id]

        try:
            context_token = self._context_tokens.get(chat_id)
            config = await self._client.get_config(chat_id, context_token)
            raw_ticket = config.get("typing_ticket")
            if isinstance(raw_ticket, str) and raw_ticket:
                self._typing_tickets[chat_id] = (raw_ticket, time.monotonic())
                return raw_ticket
        except Exception as exc:
            logger.warning("WeChatILinkChannel: failed to get typing ticket: %s", exc)
        return None

    async def start_typing(self, chat_id: str) -> None:
        ticket = await self._ensure_typing_ticket(chat_id)
        if ticket:
            try:
                await self._client.send_typing(chat_id, ticket, TypingStatus.TYPING)
            except Exception as exc:
                logger.warning("WeChatILinkChannel: send_typing failed: %s", exc)

    async def stop_typing(self, chat_id: str) -> None:
        ticket = await self._ensure_typing_ticket(chat_id)
        if ticket:
            try:
                await self._client.send_typing(chat_id, ticket, TypingStatus.CANCEL)
            except Exception as exc:
                logger.warning("WeChatILinkChannel: stop_typing failed: %s", exc)

    # ── Inbound (long-polling) ─────────────────────────────────────────

    async def _poll_loop(self) -> None:
        backoff = _INITIAL_BACKOFF

        while self._status in (ChannelStatus.RUNNING, ChannelStatus.DEGRADED):
            try:
                messages, new_buf = await self._client.get_updates(self._get_updates_buf)

                backoff = _INITIAL_BACKOFF
                self.health.record_success()

                if new_buf != self._get_updates_buf:
                    self._get_updates_buf = new_buf

                if messages:
                    logger.info("WeChatILinkChannel: received %d message(s)", len(messages))
                for ilink_msg in messages:
                    try:
                        inbound = await self._parse_message(ilink_msg)
                        if inbound:
                            await self._emit_inbound(inbound)
                    except Exception as exc:
                        logger.warning("WeChatILinkChannel: parse error: %s", exc)

            except asyncio.CancelledError:
                break

            except ChannelAuthError:
                logger.warning("WeChatILinkChannel: session expired, stopping")
                self._status = ChannelStatus.DEGRADED
                self._set_connected(False)
                break

            except Exception as exc:
                self.health.record_failure(str(exc))
                failures = self.health.consecutive_failures
                logger.warning(
                    "WeChatILinkChannel: poll error (%d/%d): %s",
                    failures,
                    _MAX_CONSECUTIVE_FAILURES,
                    exc,
                )

                if failures >= _MAX_CONSECUTIVE_FAILURES:
                    logger.warning("WeChatILinkChannel: %d consecutive failures, backing off %ds", failures, _MAX_BACKOFF)
                    self.health.record_success()
                    await asyncio.sleep(_MAX_BACKOFF)
                    backoff = _INITIAL_BACKOFF
                else:
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, _MAX_BACKOFF)

    async def _parse_message(self, ilink_msg: ILinkMessage) -> InboundMessage | None:
        """Parse ILinkMessage into InboundMessage."""
        if ilink_msg.message_type != MessageType.USER:
            return None

        from_user = ilink_msg.from_user_id
        if not from_user:
            return None

        if ilink_msg.context_token:
            self._context_tokens[from_user] = ilink_msg.context_token

        text_parts: list[str] = []
        media_list: list[MediaAttachment] = []

        for item in ilink_msg.item_list:
            await process_inbound_item(
                item,
                text_parts,
                media_list,
                self._temp_files,
                self._client.base_url,
                self._client.http,
            )

        content = "\n".join(text_parts)
        if not content and not media_list:
            return None

        is_group = bool(ilink_msg.group_id)
        chat_id: str = ilink_msg.group_id if ilink_msg.group_id else from_user

        mentioned = False
        if is_group and content:
            bot_name = self._client.credentials.ilink_bot_id if self._client.credentials else ""
            mentioned = f"@{bot_name}" in content or "@bot" in content.lower()

        metadata: dict[str, object] = {
            "context_token": ilink_msg.context_token,
            "session_id": ilink_msg.session_id,
            "message_id": ilink_msg.message_id,
            "group_id": ilink_msg.group_id,
        }

        return self._build_inbound(
            sender_id=from_user,
            content=content,
            chat_id=chat_id,
            sender_name=ilink_msg.from_user_name,
            is_group=is_group,
            mentioned=mentioned,
            media=tuple(media_list),
            metadata=metadata,
            message_id=str(ilink_msg.message_id) if ilink_msg.message_id else "",
        )
