"""WeCom (WeCom) channel — bidirectional messaging via self-built application.

Inbound: AES-CBC encrypted XML callback → decrypt → parse → emit.
Outbound: message/send API (text/markdown/media).

[INPUT]
- channels.core.base::BaseChannel, (POS: Provides FileOperationObserver.)

[OUTPUT]
- WeComChannel: WeCom self-built application bidirectional Channel

[POS]
WeCom self-built app channel: AES encrypted callbacks, multimedia send/receive,
@mention detection, OAuth token management.
"""

from __future__ import annotations

import asyncio
import logging
import tempfile
import time
from pathlib import Path

import defusedxml.ElementTree as ET
import httpx
from fastapi import Request

from app.channels.core.base import BaseChannel
from app.channels.core.credentials import credential_field, credential_spec
from app.channels.core.exceptions import ChannelAuthError, ChannelSendError
from app.channels.providers.wecom.crypto import WeComCrypto
from app.channels.rendering.renderer import render
from app.channels.security.errors import WebhookResponseError
from app.channels.types import (
    ChannelCapabilities,
    ChannelStatus,
    InboundMessage,
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

logger = logging.getLogger(__name__)

_API_BASE = "https://qyapi.weixin.qq.com/cgi-bin"
_SEND_TIMEOUT = 15.0
_UPLOAD_TIMEOUT = 30.0
_MAX_TEXT_LENGTH = 2048
_TOKEN_REFRESH_BUFFER = 300

_MSG_TYPE_TO_MEDIA: dict[str, MediaType] = {
    "image": MediaType.IMAGE,
    "voice": MediaType.AUDIO,
    "video": MediaType.VIDEO,
    "file": MediaType.DOCUMENT,
}


class WeComChannel(BaseChannel):
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

    # ── Inbound: webhook verification + encrypted callback ────

    async def verify(self, request: Request, body: bytes) -> None:
        """SignatureVerifier Protocol: validate WeCom AES-CBC signature.

        WeCom passes msg_signature, timestamp, and nonce as query parameters.
        Signature verification is combined with timestamp validation since
        WeCom computes the signature from timestamp+nonce+encrypted_body.
        """
        if not self._crypto:
            return

        msg_sig = request.query_params.get("msg_signature", "")
        timestamp_str = request.query_params.get("timestamp", "")
        nonce = request.query_params.get("nonce", "")

        if not msg_sig or not timestamp_str:
            return

        try:
            encrypted = WeComCrypto.extract_encrypted_from_xml(body.decode("utf-8"))
            if not self._crypto.verify_signature(msg_sig, timestamp_str, nonce, encrypted):
                trace_id = getattr(request.state, "_webhook_trace_id", "")
                raise WebhookResponseError(
                    status_code=403,
                    error_type="signature-invalid",
                    title="Invalid Signature",
                    detail="WeCom message signature verification failed",
                    trace_id=trace_id,
                )
        except WebhookResponseError:
            raise
        except Exception as exc:
            trace_id = getattr(request.state, "_webhook_trace_id", "")
            raise WebhookResponseError(
                status_code=403,
                error_type="signature-invalid",
                title="Invalid Signature",
                detail=f"WeCom signature verification error: {exc}",
                trace_id=trace_id,
            ) from exc

    def verify_url(self, msg_signature: str, timestamp: str, nonce: str, echostr: str) -> str:
        """Verify WeCom callback URL registration.

        Decrypts echostr and returns plaintext for the verification handshake.
        Raises ValueError if crypto is not configured or signature is invalid.
        """
        if not self._crypto:
            raise ValueError("WeCom crypto not configured")
        if not self._crypto.verify_signature(msg_signature, timestamp, nonce, echostr):
            raise ValueError("Signature verification failed")
        return self._crypto.decrypt(echostr)

    async def handle_callback(
        self,
        xml_body: str | bytes,
        *,
        msg_signature: str = "",
        timestamp: str = "",
        nonce: str = "",
    ) -> None:
        """Process a WeCom callback XML message.

        When crypto is configured, verifies signature and decrypts the payload.
        When crypto is not configured, parses the XML directly (dev mode).
        """
        raw_xml = xml_body if isinstance(xml_body, str) else xml_body.decode("utf-8")

        if self._crypto and msg_signature:
            try:
                encrypted = WeComCrypto.extract_encrypted_from_xml(raw_xml)
                if not self._crypto.verify_signature(msg_signature, timestamp, nonce, encrypted):
                    logger.warning("WeCom signature verification failed")
                    return
                raw_xml = self._crypto.decrypt(encrypted)
            except Exception as exc:
                logger.warning("WeCom decrypt failed: %s", exc)
                return

        try:
            root = ET.fromstring(raw_xml)
        except ET.ParseError as exc:
            logger.debug("WeCom XML parse failed: %s", exc)
            return

        msg = await self._parse_xml_message(root)
        if msg:
            await self._emit_inbound(msg)

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

    async def send_placeholder(self, chat_id: str, text: str, *, thread_id: str | None = None) -> str | None:
        await self._ensure_token()
        try:
            await self._api_send(chat_id, "text", {"content": text})
            return "sent"
        except ChannelSendError:
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
                MediaDownloadConfig,
                MediaDownloader,
            )

            config = MediaDownloadConfig(timeout_seconds=_UPLOAD_TIMEOUT)
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
                f"{_API_BASE}/media/upload",
                params={"access_token": self._access_token, "type": media_type},
                files={"media": (filename, data, mime_type)},
                timeout=_UPLOAD_TIMEOUT,
            )
            try:
                body = resp.json()
            except (ValueError, KeyError):
                logger.debug("WeCom media upload: non-JSON response")
                return None
            media_id = body.get("media_id")
            if not media_id:
                logger.debug(
                    "WeCom media upload failed: errcode=%s, errmsg=%s", body.get("errcode"), body.get("errmsg")
                )
                return None
            return str(media_id)
        except Exception as exc:
            logger.debug("WeCom media upload error: %s", exc)
            return None

    # ── Internal helpers ──────────────────────────────────────

    async def _parse_xml_message(self, root: ET.Element) -> InboundMessage | None:
        msg_type = root.findtext("MsgType", "")
        from_user = root.findtext("FromUserName", "")
        msg_id = root.findtext("MsgId", "")
        agent_id_str = root.findtext("AgentID", "")

        content = ""
        media_list: list[MediaAttachment] = []

        if msg_type == "text":
            content = root.findtext("Content", "")
        elif msg_type in _MSG_TYPE_TO_MEDIA:
            media_type = _MSG_TYPE_TO_MEDIA[msg_type]
            if msg_type == "image":
                pic_url = root.findtext("PicUrl", "")
                media_list.append(MediaAttachment(media_type=media_type, url=pic_url or None))
            else:
                media_id = root.findtext("MediaId", "")
                attachment = await self._download_inbound_media(media_id, media_type)
                if attachment:
                    media_list.append(attachment)
        elif msg_type == "location":
            lat = root.findtext("Location_X", "")
            lng = root.findtext("Location_Y", "")
            label = root.findtext("Label", "")
            content = f"[Location] {label} ({lat}, {lng})" if label else f"[Location] ({lat}, {lng})"
        elif msg_type == "link":
            title = root.findtext("Title", "")
            url = root.findtext("Url", "")
            content = f"[Link] {title}: {url}" if title else f"[Link] {url}"
        elif msg_type == "appmsg":
            title = root.findtext("Title", "")
            desc = root.findtext("Description", "")
            url = root.findtext("Url", "")
            parts = []
            if title:
                parts.append(f"[AppMsg] {title}")
            if desc:
                parts.append(desc)
            if url:
                parts.append(url)
            content = "\n".join(parts)

            # Try to extract media if present in WeCom AI Bot appmsg
            media_id = root.findtext("MediaId", "")
            if media_id:
                attachment = await self._download_inbound_media(media_id, MediaType.DOCUMENT)
                if attachment:
                    media_list.append(attachment)
        elif msg_type == "event":
            return None

        if not content.strip() and not media_list:
            return None

        is_group = bool(root.findtext("ChatId"))
        chat_id = root.findtext("ChatId", "") or from_user

        mentioned = not is_group
        if is_group:
            mentioned = self._check_mentioned(root)

        metadata: dict[str, object] = {
            "msg_type": msg_type,
            "agent_id": agent_id_str,
        }

        sent_at = __import__("time").time()
        create_time = root.findtext("CreateTime", "")
        if create_time:
            try:
                sent_at = float(create_time)
            except (ValueError, TypeError):
                pass

        return self._build_inbound(
            sender_id=from_user,
            content=content.strip(),
            sent_at=sent_at,
            sent_timezone="UTC",
            chat_id=chat_id,
            is_group=is_group,
            mentioned=mentioned,
            media=tuple(media_list),
            metadata=metadata,
            message_id=msg_id or "",
        )

    async def _download_inbound_media(self, media_id: str, media_type: MediaType) -> MediaAttachment | None:
        """Download inbound media from WeCom /media/get API and save to temp file."""
        if not media_id:
            return MediaAttachment(media_type=media_type)

        await self._ensure_token()
        try:
            resp = await self._http.get(
                f"{_API_BASE}/media/get",
                params={"access_token": self._access_token, "media_id": media_id},
                timeout=_UPLOAD_TIMEOUT,
            )
            if resp.status_code != 200:
                logger.debug("WeCom media download failed: HTTP %d", resp.status_code)
                return MediaAttachment(media_type=media_type)

            content_type = resp.headers.get("content-type", "")
            if "json" in content_type:
                logger.debug("WeCom media download error: %s", resp.text[:200])
                return MediaAttachment(media_type=media_type)

            ext = self._media_extension(media_type)
            suffix = f".{ext}"
            tmp = tempfile.NamedTemporaryFile(prefix="wecom_", suffix=suffix, delete=False)
            tmp.write(resp.content)
            tmp.close()

            return MediaAttachment(
                media_type=media_type,
                path=str(Path(tmp.name)),
                mime_type=content_type.split(";")[0].strip() if content_type else None,
            )
        except Exception as exc:
            logger.debug("WeCom media download error: %s", exc)
            return MediaAttachment(media_type=media_type)

    def _check_mentioned(self, root: ET.Element) -> bool:
        """Check if the bot is @mentioned in a group message."""
        content = root.findtext("Content", "")
        if not content:
            return False
        return f"@{self._agent_id}" in content or "@all" in content.lower()

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
                f"{_API_BASE}/message/send",
                params={"access_token": self._access_token},
                json=payload,
                timeout=_SEND_TIMEOUT,
            )
            if resp.status_code >= 400:
                raise ChannelSendError(f"WeCom send failed: HTTP {resp.status_code}", channel=self.name)
            try:
                data = resp.json()
            except (ValueError, KeyError) as parse_exc:
                raise ChannelSendError("WeCom send: non-JSON response", channel=self.name) from parse_exc
            errcode = data.get("errcode", 0)
            if errcode != 0:
                raise ChannelSendError(f"WeCom send error: {data.get('errmsg')} (errcode={errcode})", channel=self.name)
            return True
        except Exception as exc:
            if isinstance(exc, ChannelSendError):
                raise
            raise ChannelSendError(f"WeCom send exception: {exc}", channel=self.name) from exc

    # ── OAuth token management (with asyncio.Lock) ────────────

    async def _refresh_token(self) -> None:
        resp = await self._http.get(
            f"{_API_BASE}/gettoken",
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
        self._token_expires_at = time.monotonic() + expire - _TOKEN_REFRESH_BUFFER
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
