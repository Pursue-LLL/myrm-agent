"""DingTalk OpenAPI client — token management, messaging, and AI Card operations.

Provides async methods for sending messages, uploading media, downloading
remote resources, and managing AI Cards (streaming) via DingTalk's OpenAPI.
Handles access_token lifecycle with asyncio.Lock for concurrency protection.

[INPUT]

[OUTPUT]
- DingTalkApiClient: async API client for DingTalk OpenAPI

[POS]
DingTalk OpenAPI client. Encapsulates token management, message sending
(DM/group), media upload/download, and AI Card streaming for DingTalkChannel.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid

import httpx

from app.channels.core.exceptions import ChannelAuthError

from .helpers import normalize_file_type

logger = logging.getLogger(__name__)

_API_BASE = "https://oapi.dingtalk.com"
_API_NEW = "https://api.dingtalk.com"
_SEND_TIMEOUT = 15.0
_MEDIA_TIMEOUT = 30.0
_DOWNLOAD_TIMEOUT = 60.0
_TOKEN_REFRESH_BUFFER = 300


class DingTalkApiClient:
    """Async client for DingTalk OpenAPI with auto-refreshing token.

    Uses a shared httpx.AsyncClient for connection pooling.
    Token refresh is protected by asyncio.Lock (double-check pattern).
    """

    def __init__(self, app_key: str, app_secret: str, *, robot_code: str = "") -> None:
        self._app_key = app_key
        self._app_secret = app_secret
        self._robot_code = robot_code or app_key
        self._http = httpx.AsyncClient()
        self._access_token: str = ""
        self._token_expires_at: float = 0.0
        self._token_lock = asyncio.Lock()

    async def close(self) -> None:
        await self._http.aclose()

    # ── Token management ──────────────────────────────────────────────

    async def refresh_token(self) -> None:
        resp = await self._http.post(
            f"{_API_NEW}/v1.0/oauth2/accessToken",
            json={"appKey": self._app_key, "appSecret": self._app_secret},
            timeout=10.0,
        )
        if resp.status_code != 200:
            raise ChannelAuthError(
                f"DingTalk token refresh failed: HTTP {resp.status_code}",
                channel="dingtalk",
            )
        data = resp.json()
        self._access_token = str(data.get("accessToken", ""))
        expire = int(data.get("expireIn", 7200))
        self._token_expires_at = time.monotonic() + expire - _TOKEN_REFRESH_BUFFER

    async def ensure_token(self) -> None:
        if time.monotonic() < self._token_expires_at:
            return
        async with self._token_lock:
            if time.monotonic() < self._token_expires_at:
                return
            await self.refresh_token()

    @property
    def access_token(self) -> str:
        return self._access_token

    # ── Messaging ─────────────────────────────────────────────────────

    async def post_robot(self, url: str, payload: dict[str, object]) -> bool:
        """POST to a DingTalk robot messaging endpoint with auth header."""
        resp = await self._http.post(
            url,
            json=payload,
            headers={
                "x-acs-dingtalk-access-token": self._access_token,
                "Content-Type": "application/json",
            },
            timeout=_SEND_TIMEOUT,
        )
        if resp.status_code >= 400:
            logger.warning(
                "DingTalk API send failed: HTTP %d, %s",
                resp.status_code,
                resp.text[:200],
            )
            return False
        return True

    async def post_webhook(self, webhook_url: str, payload: dict[str, object]) -> bool:
        """POST to a DingTalk sessionWebhook URL (no auth header needed)."""
        resp = await self._http.post(webhook_url, json=payload, timeout=_SEND_TIMEOUT)
        if resp.status_code >= 400:
            logger.warning("DingTalk webhook send failed: HTTP %d", resp.status_code)
            return False
        return True

    async def send_dm_markdown(self, user_id: str, title: str, text: str) -> bool:
        msg_param = json.dumps({"title": title, "text": text}, ensure_ascii=False)
        return await self.post_robot(
            f"{_API_NEW}/v1.0/robot/oToMessages/batchSend",
            {
                "robotCode": self._robot_code,
                "userIds": [user_id],
                "msgKey": "sampleMarkdown",
                "msgParam": msg_param,
            },
        )

    async def send_group_markdown(
        self, conversation_id: str, title: str, text: str
    ) -> bool:
        msg_param = json.dumps({"title": title, "text": text}, ensure_ascii=False)
        return await self.post_robot(
            f"{_API_NEW}/v1.0/robot/groupMessages/send",
            {
                "robotCode": self._robot_code,
                "openConversationId": conversation_id,
                "msgKey": "sampleMarkdown",
                "msgParam": msg_param,
            },
        )

    async def send_image_dm(self, user_id: str, photo_url: str) -> bool:
        msg_param = json.dumps({"photoURL": photo_url}, ensure_ascii=False)
        return await self.post_robot(
            f"{_API_NEW}/v1.0/robot/oToMessages/batchSend",
            {
                "robotCode": self._robot_code,
                "userIds": [user_id],
                "msgKey": "sampleImageMsg",
                "msgParam": msg_param,
            },
        )

    async def send_file_dm(self, user_id: str, media_id: str, filename: str) -> bool:
        msg_param = json.dumps(
            {
                "mediaId": media_id,
                "fileName": filename,
                "fileType": normalize_file_type(filename),
            },
            ensure_ascii=False,
        )
        return await self.post_robot(
            f"{_API_NEW}/v1.0/robot/oToMessages/batchSend",
            {
                "robotCode": self._robot_code,
                "userIds": [user_id],
                "msgKey": "sampleFile",
                "msgParam": msg_param,
            },
        )

    # ── Media ─────────────────────────────────────────────────────────

    async def upload_media(
        self,
        data: bytes,
        media_type: str,
        filename: str,
        mime_type: str,
    ) -> str | None:
        """Upload media to DingTalk and return media_id."""
        await self.ensure_token()
        url = f"{_API_BASE}/media/upload?access_token={self._access_token}&type={media_type}"
        resp = await self._http.post(
            url,
            files={"media": (filename, data, mime_type)},
            timeout=_MEDIA_TIMEOUT,
        )
        body = resp.json()
        media_id = body.get("media_id") or body.get("mediaId")
        if not media_id:
            logger.warning("DingTalk media upload failed: %s", body)
            return None
        return str(media_id)

    async def download_url(self, url: str) -> tuple[bytes, str | None] | None:
        """Download content from an HTTP URL with SSRF protection.

        Returns (data, content_type) or None.
        """
        from app.channels.media import (
            MediaDownloadConfig,
            MediaDownloader,
        )

        config = MediaDownloadConfig(timeout_seconds=_DOWNLOAD_TIMEOUT)
        downloader = MediaDownloader(http_client=self._http, enable_default_cache=True)
        result = await downloader.download(url, config=config)
        if not result.success or not result.data:
            return None
        return result.data, result.content_type

    # ── Media Download Code Resolution ─────────────────────────────

    async def resolve_download_code(self, download_code: str) -> str | None:
        """Resolve a DingTalk downloadCode to a temporary download URL.

        DingTalk sends temporary download codes (not URLs) for media in messages.
        This calls the Robot Message File Download API to get the real URL.
        """
        await self.ensure_token()
        resp = await self._http.post(
            f"{_API_NEW}/v1.0/robot/messageFiles/download",
            json={"downloadCode": download_code, "robotCode": self._robot_code},
            headers={
                "x-acs-dingtalk-access-token": self._access_token,
                "Content-Type": "application/json",
            },
            timeout=_SEND_TIMEOUT,
        )
        if resp.status_code >= 400:
            logger.warning(
                "DingTalk resolve_download_code failed: HTTP %d, %s",
                resp.status_code,
                resp.text[:200],
            )
            return None
        data = resp.json()
        return str(data.get("downloadUrl", "")) or None

    # ── AI Card (streaming) ─────────────────────────────────────────

    async def create_and_deliver_card(
        self,
        template_id: str,
        out_track_id: str,
        open_space_id: str,
        *,
        is_group: bool,
        card_data: dict[str, str] | None = None,
    ) -> bool:
        """Create and deliver an AI Card in one call.

        Args:
            template_id: Card template ID from DingTalk Card Platform.
            out_track_id: External unique card instance ID.
            open_space_id: Target space (IM_GROUP or IM_ROBOT).
            is_group: Whether the target is a group conversation.
            card_data: Initial card variable values (key → string value).
        """
        await self.ensure_token()
        body: dict[str, object] = {
            "cardTemplateId": template_id,
            "outTrackId": out_track_id,
            "openSpaceId": open_space_id,
        }
        if card_data:
            body["cardData"] = {"cardParamMap": card_data}

        if is_group:
            body["imGroupOpenSpaceModel"] = {"supportForward": True}
            body["imGroupOpenDeliverModel"] = {"robotCode": self._robot_code}
        else:
            body["imRobotOpenSpaceModel"] = {"supportForward": True}
            body["imRobotOpenDeliverModel"] = {"spaceType": "IM_ROBOT"}

        resp = await self._http.post(
            f"{_API_NEW}/v1.0/card/instances/createAndDeliver",
            json=body,
            headers={
                "x-acs-dingtalk-access-token": self._access_token,
                "Content-Type": "application/json",
            },
            timeout=_SEND_TIMEOUT,
        )
        if resp.status_code >= 400:
            logger.warning(
                "DingTalk card createAndDeliver failed: HTTP %d, %s",
                resp.status_code,
                resp.text[:200],
            )
            return False
        return True

    async def streaming_update(
        self,
        out_track_id: str,
        key: str,
        content: str,
        *,
        is_full: bool = True,
        is_finalize: bool = False,
    ) -> bool:
        """Push a streaming update to an AI Card.

        Args:
            out_track_id: The card instance's external tracking ID.
            key: Card variable name to update (e.g. "content").
            content: New content value.
            is_full: Full replacement (True, required for markdown).
            is_finalize: Mark as final frame, ending the streaming state.
        """
        await self.ensure_token()
        body: dict[str, object] = {
            "outTrackId": out_track_id,
            "guid": uuid.uuid4().hex,
            "key": key,
            "content": content,
            "isFull": is_full,
            "isFinalize": is_finalize,
        }
        resp = await self._http.put(
            f"{_API_NEW}/v1.0/card/streaming",
            json=body,
            headers={
                "x-acs-dingtalk-access-token": self._access_token,
                "Content-Type": "application/json",
            },
            timeout=_SEND_TIMEOUT,
        )
        if resp.status_code >= 400:
            logger.warning(
                "DingTalk card streaming update failed: HTTP %d, %s",
                resp.status_code,
                resp.text[:200],
            )
            return False
        return True

    # ── Emotion (Reaction) ─────────────────────────────────────────────

    async def send_emotion(
        self,
        open_msg_id: str,
        open_conversation_id: str,
        emoji_name: str,
    ) -> bool:
        """Add an emoji reaction to a message."""
        await self.ensure_token()
        body: dict[str, object] = {
            "robotCode": self._robot_code,
            "openMsgId": open_msg_id,
            "openConversationId": open_conversation_id,
            "emotionType": 2,
            "emotionName": emoji_name,
            "textEmotion": {
                "emotionId": "2659900",
                "emotionName": emoji_name,
                "text": emoji_name,
                "backgroundId": "im_bg_1",
            },
        }
        resp = await self._http.post(
            f"{_API_NEW}/v1.0/robot/emotions/reply",
            json=body,
            headers={
                "x-acs-dingtalk-access-token": self._access_token,
                "Content-Type": "application/json",
            },
            timeout=_SEND_TIMEOUT,
        )
        if resp.status_code >= 400:
            logger.debug("DingTalk emotion reply failed: HTTP %d", resp.status_code)
            return False
        return True

    async def recall_emotion(
        self,
        open_msg_id: str,
        open_conversation_id: str,
        emoji_name: str,
    ) -> bool:
        """Remove (recall) an emoji reaction from a message."""
        await self.ensure_token()
        body: dict[str, object] = {
            "robotCode": self._robot_code,
            "openMsgId": open_msg_id,
            "openConversationId": open_conversation_id,
            "emotionType": 2,
            "emotionName": emoji_name,
            "textEmotion": {
                "emotionId": "2659900",
                "emotionName": emoji_name,
                "text": emoji_name,
                "backgroundId": "im_bg_1",
            },
        }
        resp = await self._http.post(
            f"{_API_NEW}/v1.0/robot/emotions/recall",
            json=body,
            headers={
                "x-acs-dingtalk-access-token": self._access_token,
                "Content-Type": "application/json",
            },
            timeout=_SEND_TIMEOUT,
        )
        if resp.status_code >= 400:
            logger.debug("DingTalk emotion recall failed: HTTP %d", resp.status_code)
            return False
        return True

    # ── Stream API ────────────────────────────────────────────────────

    async def open_stream_connection(self) -> tuple[str, str]:
        """Open a DingTalk Stream connection. Returns (endpoint, ticket)."""
        resp = await self._http.post(
            f"{_API_NEW}/v1.0/gateway/connections/open",
            headers={"Content-Type": "application/json"},
            json={
                "clientId": self._app_key,
                "clientSecret": self._app_secret,
                "subscriptions": [
                    {"type": "EVENT", "topic": "/v1.0/im/bot/messages/get"},
                ],
            },
            timeout=10.0,
        )
        if resp.status_code >= 400:
            raise ChannelAuthError(
                f"DingTalk stream connection failed: HTTP {resp.status_code}",
                channel="dingtalk",
            )
        data = resp.json()
        return str(data.get("endpoint", "")), str(data.get("ticket", ""))
