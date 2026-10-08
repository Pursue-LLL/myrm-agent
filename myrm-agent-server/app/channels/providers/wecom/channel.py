"""WeCom (WeCom) channel — bidirectional messaging via self-built application.

Inbound: AES-CBC encrypted XML callback → decrypt → parse → emit.
Outbound: message/send API (text/markdown/media).

[INPUT]
- channels.core.base::BaseChannel, (POS: Provides FileOperationObserver.)
- channels.providers.wecom.inbound::WeComInboundMixin (POS: webhook verification and encrypted callback handling)

[OUTPUT]
- WeComChannel: WeCom self-built application bidirectional Channel

[POS]
WeCom self-built app channel: AES encrypted callbacks, multimedia send/receive,
@mention detection, OAuth token management.
"""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path

import httpx

from app.channels.core.base import BaseChannel
from app.channels.core.credentials import credential_field, credential_spec
from app.channels.core.exceptions import ChannelAuthError, ChannelSendError
from app.channels.providers.wecom.crypto import WeComCrypto
from app.channels.providers.wecom.user_resolver import WeComUserResolver
from app.channels.rendering.renderer import render
from app.channels.types import (
    ChannelCapabilities,
    ChannelStatus,
    MediaAttachment,
    MediaType,
    OutboundMessage,
    RenderStyle,
)
from app.channels.types.status import (
    ChannelIssue,
    IssueKind,
    IssueSeverity,
)

from .constants import API_BASE, SEND_TIMEOUT, TOKEN_REFRESH_BUFFER, UPLOAD_TIMEOUT
from .inbound import WeComInboundMixin

logger = logging.getLogger(__name__)

_MAX_TEXT_LENGTH = 2048


class WeComChannel(WeComInboundMixin, BaseChannel):
    """WeCom (WeCom) self-built application channel.

    Supports AES-CBC encrypted webhook callbacks, multi-format outbound
    messages (text/markdown/image/voice/video/file), group chat with
    @mention detection, and structured diagnostics.
    """

    name = "wecom"
    credential_spec = credential_spec(
        "wecomCredentials",
        corp_id=credential_field("corpId", "WECOM_CORP_ID"),
        corp_secret=credential_field("corpSecret", "WECOM_CORP_SECRET"),
        agent_id=credential_field("agentId", "WECOM_AGENT_ID"),
        token=credential_field("token", "WECOM_TOKEN"),
        encoding_aes_key=credential_field("encodingAesKey", "WECOM_ENCODING_AES_KEY"),
    )
    capabilities = ChannelCapabilities(
        text=True,
        markdown=True,
        media=True,
        file_upload=True,
        typing_indicator=False,
        max_text_length=_MAX_TEXT_LENGTH,
    )
    render_style = RenderStyle(
        format="markdown",
        max_text_length=_MAX_TEXT_LENGTH,
    )

    def __init__(
        self,
        corp_id: str,
        corp_secret: str,
        agent_id: str | int,
        *,
        token: str = "",
        encoding_aes_key: str = "",
    ) -> None:
        super().__init__()
        self._corp_id = corp_id
        self._corp_secret = corp_secret
        self._agent_id = int(agent_id) if agent_id else 0

        self._crypto: WeComCrypto | None = None
        if token and encoding_aes_key:
            self._crypto = WeComCrypto(token, encoding_aes_key, corp_id)

        self._http = httpx.AsyncClient()
        self._access_token: str = ""
        self._token_expires_at: float = 0.0
        self._token_lock = asyncio.Lock()
        self._user_resolver = WeComUserResolver(self)

    # ── Lifecycle ──────────────────────────────────────────────

    async def start(self) -> None:
        if not self._corp_id or not self._corp_secret:
            logger.info("WeCom credentials not configured; channel idle")
            return
        try:
            await self._refresh_token()
        except Exception as exc:
            logger.warning("WeComChannel: startup failed: %s", exc)
            self._status = ChannelStatus.ERROR
            await self._http.aclose()
            return
        self._status = ChannelStatus.RUNNING
        self._set_connected(True)
        logger.info("WeComChannel: started (agent_id=%d)", self._agent_id)

    async def stop(self) -> None:
        self._set_connected(False)
        self._status = ChannelStatus.STOPPED
        await self._http.aclose()
        logger.info("WeComChannel: stopped")

    async def health_check(self) -> bool:
        if self._status not in (ChannelStatus.RUNNING, ChannelStatus.DEGRADED):
            return False
        try:
            await self._ensure_token()
            return bool(self._access_token)
        except Exception:
            return False

    def collect_issues(self) -> list[ChannelIssue]:
        issues = super().collect_issues()
        if not self._corp_id:
            issues.append(
                ChannelIssue(
                    kind=IssueKind.CONFIG,
                    severity=IssueSeverity.ERROR,
                    message="Corp ID is not configured",
                    fix="Set WECOM_CORP_ID or configure in Settings → Channels → WeCom",
                )
            )
        if not self._corp_secret:
            issues.append(
                ChannelIssue(
                    kind=IssueKind.CONFIG,
                    severity=IssueSeverity.ERROR,
                    message="Corp secret is not configured",
                    fix="Set WECOM_CORP_SECRET or configure in Settings → Channels → WeCom",
                )
            )
        if not self._crypto:
            issues.append(
                ChannelIssue(
                    kind=IssueKind.CONFIG,
                    severity=IssueSeverity.WARNING,
                    message="Encryption not configured — webhook callbacks will not work",
                    fix="Set WECOM_TOKEN and WECOM_ENCODING_AES_KEY",
                )
            )
        if self._status == ChannelStatus.ERROR and not issues:
            issues.append(
                ChannelIssue(
                    kind=IssueKind.AUTH,
                    severity=IssueSeverity.ERROR,
                    message="Access token acquisition failed",
                    fix="Verify Corp ID and Corp Secret in WeCom admin console",
                )
            )
        return issues

    # ── Outbound: send / placeholder ──────────────────────────

    async def send(self, msg: OutboundMessage) -> str | None:
        await self._ensure_token()

        if msg.media:
            for attachment in msg.media:
                await self._send_media(msg.recipient_id, attachment)

        if msg.content:
            from app.channels.reliability.retry import send_with_retry

            chunks = render(msg, self.render_style)
            for chunk in chunks:
                try:
                    await send_with_retry(
                        self._api_send,
                        msg.recipient_id,
                        "markdown",
                        {"content": chunk},
                        config=self.retry_config,
                        should_retry=self.should_retry,
                        label="wecom:chunk",
                    )
                except Exception as exc:
                    logger.error("WeCom chunk send failed after retries: %s", exc)
                    raise ChannelSendError(
                        f"WeCom chunk send failed: {exc}",
                        channel=self.name,
                        retriable=False,
                    ) from exc
        return None

    async def send_placeholder(
        self,
        chat_id: str,
        text: str,
        *,
        thread_id: str | None = None,
    ) -> str | None:
        """WeCom self-built apps do not support editing plain messages.

        Returns None to disable placeholder sending and avoid leaving orphan messages.
        """
        return None

    # ── Media upload + send ───────────────────────────────────

    async def _send_media(self, recipient_id: str, attachment: MediaAttachment) -> None:
        """Upload media to WeCom temporary storage and send to user."""
        media_data: bytes | None = None

        if attachment.path:
            try:
                media_data = Path(attachment.path).read_bytes()
            except Exception as exc:
                logger.debug("WeCom media read failed: %s", exc)
                return
        elif attachment.url:
            from app.channels.media import (
                MAX_FORWARD_DOWNLOAD_BYTES,
                MediaDownloadConfig,
                MediaDownloader,
            )

            config = MediaDownloadConfig(
                timeout_seconds=UPLOAD_TIMEOUT,
                max_size_bytes=MAX_FORWARD_DOWNLOAD_BYTES,
            )
            downloader = MediaDownloader(http_client=self._http, enable_default_cache=True)
            result = await downloader.download(attachment.url, config=config)
            if result.success and result.data:
                media_data = result.data

        if not media_data:
            return

        wecom_type = self._media_type_to_wecom(attachment.media_type)
        filename = attachment.filename or f"file.{self._media_extension(attachment.media_type)}"
        mime = attachment.mime_type or "application/octet-stream"

        media_id = await self._upload_media(wecom_type, media_data, filename, mime)
        if not media_id:
            return

        try:
            await self._api_send(recipient_id, wecom_type, {"media_id": media_id})
        except ChannelSendError as exc:
            logger.debug("WeCom media send failed: %s", exc)

    async def _upload_media(self, media_type: str, data: bytes, filename: str, mime_type: str) -> str | None:
        """Upload media to WeCom and return media_id."""
        await self._ensure_token()
        try:
            resp = await self._http.post(
                f"{API_BASE}/media/upload",
                params={"access_token": self._access_token, "type": media_type},
                files={"media": (filename, data, mime_type)},
                timeout=UPLOAD_TIMEOUT,
            )
            try:
                body = resp.json()
            except (ValueError, KeyError):
                logger.debug("WeCom media upload: non-JSON response")
                return None
            media_id = body.get("media_id")
            if not media_id:
                logger.debug(
                    "WeCom media upload failed: errcode=%s, errmsg=%s",
                    body.get("errcode"),
                    body.get("errmsg"),
                )
                return None
            return str(media_id)
        except Exception as exc:
            logger.debug("WeCom media upload error: %s", exc)
            return None

    # ── Internal helpers ──────────────────────────────────────

    async def _api_send(self, user_id: str, msg_type: str, body: dict[str, str]) -> bool:
        """Send a message via WeCom message/send API. Raises ChannelSendError on failure."""
        payload: dict[str, str | int | dict[str, str]] = {
            "touser": user_id,
            "msgtype": msg_type,
            "agentid": self._agent_id,
            msg_type: body,
        }
        try:
            resp = await self._http.post(
                f"{API_BASE}/message/send",
                params={"access_token": self._access_token},
                json=payload,
                timeout=SEND_TIMEOUT,
            )
            if resp.status_code >= 400:
                raise ChannelSendError(f"WeCom send failed: HTTP {resp.status_code}", channel=self.name)
            try:
                data = resp.json()
            except (ValueError, KeyError) as parse_exc:
                raise ChannelSendError("WeCom send: non-JSON response", channel=self.name) from parse_exc
            errcode = data.get("errcode", 0)
            if errcode != 0:
                raise ChannelSendError(
                    f"WeCom send error: {data.get('errmsg')} (errcode={errcode})",
                    channel=self.name,
                )
            return True
        except Exception as exc:
            if isinstance(exc, ChannelSendError):
                raise
            raise ChannelSendError(f"WeCom send exception: {exc}", channel=self.name) from exc

    async def api_get_user(self, user_id: str) -> dict[str, object] | None:
        """Fetch a WeCom user's contact info by userid.

        Returns the user object (with ``name``) or None on failure.
        """
        if not user_id:
            return None
        await self._ensure_token()
        try:
            resp = await self._http.get(
                f"{API_BASE}/user/get",
                params={"access_token": self._access_token, "userid": user_id},
                timeout=10.0,
            )
            if resp.status_code >= 400:
                logger.debug("WeCom user/get failed: HTTP %d", resp.status_code)
                return None
            data = resp.json()
            if data.get("errcode", 0) != 0:
                logger.debug("WeCom user/get error: %s", data.get("errmsg"))
                return None
            return data
        except Exception as exc:
            logger.debug("WeCom user/get exception: %s", exc)
            return None

    # ── OAuth token management (with asyncio.Lock) ────────────

    async def _refresh_token(self) -> None:
        resp = await self._http.get(
            f"{API_BASE}/gettoken",
            params={"corpid": self._corp_id, "corpsecret": self._corp_secret},
            timeout=10.0,
        )
        if resp.status_code != 200:
            raise ChannelAuthError(
                f"WeCom token refresh failed: HTTP {resp.status_code}",
                channel="wecom",
            )
        try:
            data = resp.json()
        except (ValueError, KeyError) as exc:
            raise ChannelAuthError(
                f"WeCom token response not JSON: {exc}",
                channel="wecom",
            ) from exc
        if data.get("errcode", 0) != 0:
            raise ChannelAuthError(
                f"WeCom token error: {data.get('errmsg')}",
                channel="wecom",
            )
        self._access_token = str(data.get("access_token", ""))
        expire = int(data.get("expires_in", 7200))
        self._token_expires_at = time.monotonic() + expire - TOKEN_REFRESH_BUFFER
        logger.info("WeCom token refreshed, expires in %ds", expire)

    async def _ensure_token(self) -> None:
        """Double-checked locking for concurrent token refresh."""
        if time.monotonic() < self._token_expires_at:
            return
        async with self._token_lock:
            if time.monotonic() >= self._token_expires_at:
                await self._refresh_token()

    @staticmethod
    def _media_type_to_wecom(media_type: MediaType) -> str:
        mapping: dict[MediaType, str] = {
            MediaType.IMAGE: "image",
            MediaType.AUDIO: "voice",
            MediaType.VIDEO: "video",
            MediaType.DOCUMENT: "file",
        }
        return mapping.get(media_type, "file")

    @staticmethod
    def _media_extension(media_type: MediaType) -> str:
        mapping: dict[MediaType, str] = {
            MediaType.IMAGE: "png",
            MediaType.AUDIO: "amr",
            MediaType.VIDEO: "mp4",
            MediaType.DOCUMENT: "bin",
        }
        return mapping.get(media_type, "bin")
