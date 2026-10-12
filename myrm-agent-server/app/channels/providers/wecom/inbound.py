"""WeCom inbound: webhook signature verification, encrypted XML callback handling and inbound media download.

[INPUT]
- channels.core.base::BaseChannel (POS: Channel abstract base class; supplies the host members the mixin calls)
- channels.providers.wecom.crypto::WeComCrypto (POS: AES-CBC callback crypto)
- channels.providers.wecom.user_resolver::WeComUserResolver (POS: sender display-name resolution)
- channels.security.errors::WebhookResponseError (POS: RFC 7807 webhook error response)
- channels.types::InboundMessage, MediaAttachment, MediaType (POS: channel message value types)

[OUTPUT]
- WeComInboundMixin: verify / verify_url / handle_callback and the XML parser used by WeComChannel

[POS]
Inbound half of WeComChannel. The host owns credentials, token management and outbound API calls; the mixin only
verifies, decrypts and converts callbacks into InboundMessage.
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

import defusedxml.ElementTree as ET
import httpx
from fastapi import Request

from app.channels.core.base import BaseChannel
from app.channels.providers.wecom.crypto import WeComCrypto
from app.channels.providers.wecom.user_resolver import WeComUserResolver
from app.channels.security.errors import WebhookResponseError
from app.channels.types import (
    InboundMessage,
    MediaAttachment,
    MediaType,
)

from .constants import API_BASE, UPLOAD_TIMEOUT

logger = logging.getLogger(__name__)

_MSG_TYPE_TO_MEDIA: dict[str, MediaType] = {
    "image": MediaType.IMAGE,
    "voice": MediaType.AUDIO,
    "video": MediaType.VIDEO,
    "file": MediaType.DOCUMENT,
}


class WeComInboundMixin(BaseChannel):
    """WeCom self-built application inbound handling for ``WeComChannel``.

    Requires the host class to provide the attributes and helpers below plus ``_emit_inbound`` /
    ``_build_inbound`` from ``BaseChannel``.
    """

    _agent_id: int
    _crypto: WeComCrypto | None
    _http: httpx.AsyncClient
    _access_token: str
    _user_resolver: WeComUserResolver

    if TYPE_CHECKING:

        async def _ensure_token(self) -> None: ...

        @staticmethod
        def _media_extension(media_type: MediaType) -> str: ...

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
                detail="WeCom signature verification error",
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
            sender_name=await self._resolve_sender_name(from_user),
        )

    async def _resolve_sender_name(self, sender_id: str) -> str | None:
        """Resolve a WeCom sender's display name via contact API (fail-open).

        Returns None when the ID is missing, resolution fails, or the user
        cannot be found — callers fall back to the opaque userid.
        """
        if not sender_id:
            return None
        try:
            return await self._user_resolver.resolve_user(sender_id)
        except Exception:
            logger.debug("Failed to resolve WeCom sender name for %s", sender_id)
            return None

    async def _download_inbound_media(self, media_id: str, media_type: MediaType) -> MediaAttachment | None:
        """Download inbound media from WeCom /media/get API and save to temp file."""
        if not media_id:
            return MediaAttachment(media_type=media_type)

        await self._ensure_token()
        try:
            resp = await self._http.get(
                f"{API_BASE}/media/get",
                params={"access_token": self._access_token, "media_id": media_id},
                timeout=UPLOAD_TIMEOUT,
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
