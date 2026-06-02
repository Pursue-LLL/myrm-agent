"""WeChat Official Account channel — bidirectional messaging via Official Account API.

Inbound: HTTP callback (XML) → _parse_xml_message → _emit_inbound
  - Supports text, image, voice, video messages
Outbound: Customer message API (text, image, news)

[INPUT]
- channels.core.base::BaseChannel (POS: Channel abstract base class)
- channels.types::OutboundMessage, (POS: Provides ArtifactInfo, infer_language, infer_artifact_type.)

[OUTPUT]
- WeChatOfficialChannel: WeChat Official Account bidirectional messaging Channel

[POS]
WeChat Official Account channel implementation. Supports passive replies,
customer service messages, rich-media (news) messages, and media send/receive.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
import time
from pathlib import Path

import defusedxml.ElementTree as ET
import httpx

from app.channels.core.base import BaseChannel
from app.channels.core.credentials import credential_field, credential_spec
from app.channels.core.exceptions import (
    ChannelAuthError,
    ChannelConnectionError,
    ChannelSendError,
)
from app.channels.rendering.renderer import render
from app.channels.types import (
    ChannelCapabilities,
    ChannelStatus,
    InboundMessage,
    MediaAttachment,
    MediaType,
    OutboundMessage,
    RenderStyle,
)

logger = logging.getLogger(__name__)

_API_BASE = "https://api.weixin.qq.com/cgi-bin"
_SEND_TIMEOUT = 15.0
_MAX_TEXT_LENGTH = 600
_TOKEN_REFRESH_BUFFER = 300
_TOKEN_EXPIRED_ERRCODES = {40001, 42001}


class WeChatOfficialChannel(BaseChannel):
    """WeChat Official Account channel (Official Account API)."""

    name = "wechat_official"
    credential_spec = credential_spec(
        "wechatOfficialCredentials",
        app_id=credential_field("appId", "WECHAT_OFFICIAL_APP_ID"),
        app_secret=credential_field("appSecret", "WECHAT_OFFICIAL_APP_SECRET"),
        token=credential_field("token", "WECHAT_OFFICIAL_TOKEN"),
        encoding_aes_key=credential_field("encodingAesKey", "WECHAT_OFFICIAL_ENCODING_AES_KEY"),
    )
    capabilities = ChannelCapabilities(
        text=True,
        media=True,
        voice_message=True,
        typing_indicator=False,
        max_text_length=_MAX_TEXT_LENGTH,
    )
    render_style = RenderStyle(
        format="text",
        max_text_length=_MAX_TEXT_LENGTH,
    )

    def __init__(
        self,
        app_id: str,
        app_secret: str,
        *,
        token: str = "",
        encoding_aes_key: str = "",
    ) -> None:
        super().__init__()
        self._app_id = app_id
        self._app_secret = app_secret
        self._token = token
        self._encoding_aes_key = encoding_aes_key
        self._http = httpx.AsyncClient()
        self._access_token: str = ""
        self._token_expires_at: float = 0.0
        self._token_lock = asyncio.Lock()

    async def start(self) -> None:
        if not self._app_id or not self._app_secret:
            logger.info("WeChat credentials not configured; channel idle")
            return
        try:
            await self._refresh_token()
        except Exception as exc:
            logger.warning("WeChatChannel: startup failed: %s", exc)
            self._status = ChannelStatus.ERROR
            await self._http.aclose()
            return
        self._status = ChannelStatus.RUNNING
        self._set_connected(True)
        logger.info("WeChatOfficialChannel: started")

    async def stop(self) -> None:
        self._set_connected(False)
        self._status = ChannelStatus.STOPPED
        await self._http.aclose()
        logger.info("WeChatOfficialChannel: stopped")

    async def health_check(self) -> bool:
        if self._status not in (ChannelStatus.RUNNING, ChannelStatus.DEGRADED):
            return False
        try:
            await self._ensure_token()
            return bool(self._access_token)
        except Exception:
            return False

    async def send(self, msg: OutboundMessage) -> str | None:
        await self._ensure_token()

        if msg.media:
            for attachment in msg.media:
                await self._send_media_message(msg.recipient_id, attachment)

        if msg.content:
            from app.channels.reliability.retry import send_with_retry

            chunks = render(msg, self.render_style)
            for chunk in chunks:
                try:
                    await send_with_retry(
                        self._send_customer_message,
                        msg.recipient_id,
                        chunk,
                        config=self.retry_config,
                        should_retry=self.should_retry,
                        label="wechat_official:chunk",
                    )
                except Exception as exc:
                    logger.error("WeChat chunk send failed after retries: %s", exc)
                    raise ChannelSendError(
                        f"WeChat chunk send failed: {exc}",
                        channel=self.name,
                        retriable=False,
                    ) from exc
        return None

    def verify_url(self, signature: str, timestamp: str, nonce: str) -> bool:
        """Verify WeChat callback URL and prevent replay attacks."""
        try:
            ts = int(timestamp)
            if abs(time.time() - ts) > 300:  # 5 minutes replay protection
                logger.warning("WeChat signature verification failed: timestamp expired (replay attack protection)")
                return False
        except ValueError:
            return False

        sort_list = sorted([self._token, timestamp, nonce])
        sha1 = hashlib.sha1("".join(sort_list).encode("utf-8")).hexdigest()
        return hmac.compare_digest(sha1, signature)

    async def handle_callback(self, xml_body: str | bytes) -> str | None:
        """Process a WeChat callback XML message. Returns passive reply XML or None."""
        try:
            root = ET.fromstring(xml_body if isinstance(xml_body, str) else xml_body.decode("utf-8"))
        except ET.ParseError as exc:
            logger.debug("WeChat XML parse failed: %s", exc)
            return None

        msg = self._parse_xml_message(root)
        if msg:
            await self._emit_inbound(msg)

        return "success"

    def _parse_xml_message(self, root: ET.Element) -> InboundMessage | None:
        msg_type = root.findtext("MsgType", "")
        from_user = root.findtext("FromUserName", "")
        msg_id = root.findtext("MsgId", "")

        content = ""
        media_list: list[MediaAttachment] = []

        if msg_type == "text":
            content = root.findtext("Content", "")
        elif msg_type == "image":
            pic_url = root.findtext("PicUrl", "")
            media_list.append(MediaAttachment(media_type=MediaType.IMAGE, url=pic_url))
        elif msg_type == "voice":
            recognition = root.findtext("Recognition", "")
            if recognition:
                content = recognition
            else:
                media_list.append(MediaAttachment(media_type=MediaType.AUDIO))
        elif msg_type == "video" or msg_type == "shortvideo":
            media_list.append(MediaAttachment(media_type=MediaType.VIDEO))
        elif msg_type == "event":
            return None

        if not content.strip() and not media_list:
            return None

        metadata: dict[str, object] = {
            "msg_type": msg_type,
            "to_user": root.findtext("ToUserName", ""),
        }

        return self._build_inbound(
            sender_id=from_user,
            content=content.strip(),
            chat_id=from_user,
            is_group=False,
            mentioned=True,
            media=tuple(media_list),
            metadata=metadata,
            message_id=msg_id or "",
        )

    async def _send_customer_message(self, openid: str, text: str) -> None:
        payload: dict[str, object] = {
            "touser": openid,
            "msgtype": "text",
            "text": {"content": text},
        }
        await self._call_customer_api(payload)

    async def _send_media_message(self, openid: str, attachment: MediaAttachment) -> None:
        """Send media via customer message API (requires media_id upload)."""
        media_id = await self._upload_temp_media(attachment)
        if not media_id:
            return

        type_map = {
            MediaType.IMAGE: "image",
            MediaType.AUDIO: "voice",
            MediaType.VIDEO: "video",
        }
        wx_type = type_map.get(attachment.media_type)
        if not wx_type:
            logger.debug("WeChat: unsupported media type %s", attachment.media_type)
            return

        payload: dict[str, object] = {
            "touser": openid,
            "msgtype": wx_type,
            wx_type: {"media_id": media_id},
        }
        await self._call_customer_api(payload)

    async def _call_customer_api(self, payload: dict[str, object], *, _retried: bool = False) -> None:
        resp = await self._http.post(
            f"{_API_BASE}/message/custom/send",
            params={"access_token": self._access_token},
            json=payload,
            timeout=_SEND_TIMEOUT,
        )
        if resp.status_code >= 400:
            raise ChannelConnectionError(f"WeChat API HTTP {resp.status_code}", channel="wechat_official")
        data = resp.json()
        errcode = data.get("errcode", 0)
        if errcode == 0:
            return
        if errcode in _TOKEN_EXPIRED_ERRCODES and not _retried:
            await self._refresh_token()
            await self._call_customer_api(payload, _retried=True)
            return
        raise ChannelConnectionError(
            f"WeChat API error: {data.get('errmsg')} (errcode={errcode})",
            channel="wechat_official",
        )

    async def _upload_temp_media(self, attachment: MediaAttachment) -> str | None:
        """Upload media to WeChat temporary material API, return media_id."""
        type_map = {
            MediaType.IMAGE: "image",
            MediaType.AUDIO: "voice",
            MediaType.VIDEO: "video",
        }
        wx_type = type_map.get(attachment.media_type)
        if not wx_type:
            return None

        media_bytes: bytes | None = None
        filename = "media"

        if attachment.url:
            from app.channels.media import (
                MediaDownloadConfig,
                MediaDownloader,
            )

            config = MediaDownloadConfig(timeout_seconds=30.0)
            downloader = MediaDownloader(http_client=self._http, enable_default_cache=True)
            result = await downloader.download(attachment.url, config=config)
            if not result.success or not result.data:
                return None
            media_bytes = result.data
        elif attachment.path:
            file_path = Path(attachment.path)
            if not file_path.exists():
                logger.warning("WeChat: media File not found: %s", attachment.path)
                return None
            media_bytes = file_path.read_bytes()
            filename = attachment.filename or file_path.name
        else:
            return None

        resp = await self._http.post(
            f"{_API_BASE}/media/upload",
            params={"access_token": self._access_token, "type": wx_type},
            files={"media": (filename, media_bytes)},
            timeout=30.0,
        )
        data = resp.json()
        media_id = data.get("media_id")
        if not isinstance(media_id, str):
            logger.warning("WeChat: upload failed: %s", data)
            return None
        return media_id

    def build_passive_reply(self, to_user: str, from_user: str, content: str) -> str:
        """Build passive reply XML for WeChat callback response."""
        return (
            "<xml>"
            f"<ToUserName><![CDATA[{to_user}]]></ToUserName>"
            f"<FromUserName><![CDATA[{from_user}]]></FromUserName>"
            f"<CreateTime>{int(time.time())}</CreateTime>"
            "<MsgType><![CDATA[text]]></MsgType>"
            f"<Content><![CDATA[{content}]]></Content>"
            "</xml>"
        )

    async def _refresh_token(self) -> None:
        resp = await self._http.get(
            f"{_API_BASE}/token",
            params={
                "grant_type": "client_credential",
                "appid": self._app_id,
                "secret": self._app_secret,
            },
            timeout=10.0,
        )
        if resp.status_code != 200:
            raise ChannelAuthError(
                f"WeChat token refresh failed: HTTP {resp.status_code}",
                channel="wechat",
            )
        data = resp.json()
        if "errcode" in data and data["errcode"] != 0:
            raise ChannelAuthError(
                f"WeChat token error: {data.get('errmsg')}",
                channel="wechat",
            )
        self._access_token = str(data.get("access_token", ""))
        expire = int(data.get("expires_in", 7200))
        self._token_expires_at = time.monotonic() + expire - _TOKEN_REFRESH_BUFFER

    async def _ensure_token(self) -> None:
        """Double-checked locking for concurrent token refresh."""
        if time.monotonic() < self._token_expires_at:
            return
        async with self._token_lock:
            if time.monotonic() >= self._token_expires_at:
                await self._refresh_token()
