"""DingTalk OpenAPI client — token management and message operations.

Provides async methods for sending messages, uploading media, and downloading
remote resources via DingTalk's OpenAPI. Handles access_token lifecycle
(auto-refresh on 2h TTL).

[INPUT]
- client_id (AppKey), client_secret (AppSecret) from DingTalk Open Platform

[OUTPUT]
- DingTalkClient: async API client for DingTalk OpenAPI

[POS]
钉钉 OpenAPI 客户端。封装 token 管理和消息/媒体操作，
为 DingTalkChannel 提供底层 HTTP API 调用能力。
"""

from __future__ import annotations

import json
import logging
import time

import httpx

from app.config.settings import settings

from .http_timeout import resolve_timeout

logger = logging.getLogger(__name__)

_TOKEN_URL = "https://api.dingtalk.com/v1.0/oauth2/accessToken"
_SEND_URL = "https://api.dingtalk.com/v1.0/robot/oToMessages/batchSend"
_GROUP_SEND_URL = "https://api.dingtalk.com/v1.0/robot/groupMessages/send"
_MEDIA_UPLOAD_URL = "https://oapi.dingtalk.com/media/upload"
_TOKEN_REFRESH_BUFFER = 300


def _request_timeout() -> float:
    return resolve_timeout(settings.channel_dingtalk.timeout)


def _media_timeout() -> float:
    return resolve_timeout(settings.channel_dingtalk.media_timeout)


def _download_timeout() -> float:
    return resolve_timeout(settings.channel_dingtalk.download_timeout)


class DingTalkClient:
    """Async client for DingTalk OpenAPI with auto-refreshing token.

    Uses a shared httpx.AsyncClient for connection pooling.
    Call ``close()`` during application shutdown to release resources.
    """

    def __init__(self, client_id: str, client_secret: str) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._token: str = ""
        self._token_expires_at: float = 0.0
        self._http: httpx.AsyncClient | None = None

    def _get_http(self, *, timeout: float | None = None) -> httpx.AsyncClient:
        effective_timeout = timeout if timeout is not None else _request_timeout()
        if self._http is None or self._http.is_closed:
            self._http = httpx.AsyncClient(timeout=effective_timeout)
        return self._http

    async def close(self) -> None:
        if self._http and not self._http.is_closed:
            await self._http.aclose()
            self._http = None

    async def _ensure_token(self) -> str:
        if self._token and time.monotonic() < self._token_expires_at:
            return self._token

        http = self._get_http()
        resp = await http.post(
            _TOKEN_URL,
            json={"appKey": self._client_id, "appSecret": self._client_secret},
        )
        resp.raise_for_status()
        data = resp.json()

        token = data.get("accessToken")
        if not token:
            raise RuntimeError(f"DingTalk token error: {data}")

        self._token = token
        expire = int(data.get("expireIn", 7200))
        self._token_expires_at = time.monotonic() + expire - _TOKEN_REFRESH_BUFFER
        logger.warning("DingTalk token refreshed, expires in %ds", expire)
        return self._token

    async def verify_token(self) -> bool:
        try:
            await self._ensure_token()
            return True
        except Exception:
            return False

    async def _post_robot(self, url: str, payload: dict[str, object], msg_key: str) -> bool:
        """POST to a DingTalk robot messaging endpoint with auth."""
        token = await self._ensure_token()
        http = self._get_http()
        resp = await http.post(
            url,
            json=payload,
            headers={"x-acs-dingtalk-access-token": token},
        )
        if resp.status_code != 200:
            logger.warning("DingTalk send failed: msgKey=%s HTTP %d, %s", msg_key, resp.status_code, resp.text[:200])
            return False
        return True

    def _msg_param_json(self, msg_param: dict[str, str]) -> str:
        return json.dumps(msg_param, ensure_ascii=False)

    async def _send_dm(self, ding_user_id: str, msg_key: str, msg_param: dict[str, str]) -> bool:
        """Send a robot batch message to a single user (DM)."""
        return await self._post_robot(
            _SEND_URL,
            {
                "robotCode": self._client_id,
                "userIds": [ding_user_id],
                "msgKey": msg_key,
                "msgParam": self._msg_param_json(msg_param),
            },
            msg_key,
        )

    async def _send_group(self, conversation_id: str, msg_key: str, msg_param: dict[str, str]) -> bool:
        """Send a robot message to a group conversation."""
        return await self._post_robot(
            _GROUP_SEND_URL,
            {
                "robotCode": self._client_id,
                "openConversationId": conversation_id,
                "msgKey": msg_key,
                "msgParam": self._msg_param_json(msg_param),
            },
            msg_key,
        )

    async def send_markdown(self, ding_user_id: str, title: str, content: str) -> bool:
        """Send a Markdown message to a user via robot batch API."""
        return await self._send_dm(ding_user_id, "sampleMarkdown", {"title": title, "text": content})

    async def send_text(self, ding_user_id: str, content: str) -> bool:
        """Send a plain text message to a user."""
        return await self._send_dm(ding_user_id, "sampleText", {"content": content})

    async def send_group_markdown(self, conversation_id: str, title: str, content: str) -> bool:
        """Send a Markdown message to a group conversation."""
        return await self._send_group(conversation_id, "sampleMarkdown", {"title": title, "text": content})

    async def send_group_text(self, conversation_id: str, content: str) -> bool:
        """Send a plain text message to a group conversation."""
        return await self._send_group(conversation_id, "sampleText", {"content": content})

    async def send_image(self, ding_user_id: str, photo_url: str) -> bool:
        """Send an image message (URL or media_id) to a user."""
        return await self._send_dm(ding_user_id, "sampleImageMsg", {"photoURL": photo_url})

    async def send_file(self, ding_user_id: str, media_id: str, filename: str, file_type: str) -> bool:
        """Send a file message via uploaded media_id."""
        return await self._send_dm(
            ding_user_id,
            "sampleFile",
            {
                "mediaId": media_id,
                "fileName": filename,
                "fileType": file_type,
            },
        )

    async def download_url(self, url: str) -> tuple[bytes, str | None] | None:
        """Download content from an HTTP URL.

        Returns (data, content_type) or None on failure.
        """
        http = self._get_http()
        try:
            resp = await http.get(url, follow_redirects=True, timeout=_download_timeout())
            if resp.status_code >= 400:
                logger.warning("DingTalk download failed: HTTP %d, url=%s", resp.status_code, url.split("?")[0])
                return None
            content_type = (resp.headers.get("content-type") or "").split(";")[0].strip() or None
            return resp.content, content_type
        except Exception as exc:
            safe_url = url.split("?")[0] if url else ""
            logger.warning("DingTalk download error: %s, url=%s", exc, safe_url)
            return None

    async def upload_media(self, data: bytes, media_type: str, filename: str, mime_type: str) -> str | None:
        """Upload media and return media_id.

        media_type: image | voice | video | file
        """
        token = await self._ensure_token()
        http = self._get_http()
        url = f"{_MEDIA_UPLOAD_URL}?access_token={token}&type={media_type}"
        resp = await http.post(
            url,
            files={"media": (filename, data, mime_type)},
            timeout=_media_timeout(),
        )
        body = resp.json()
        media_id = body.get("media_id") or body.get("mediaId")
        if not media_id:
            logger.warning("DingTalk media upload failed: %s", body)
            return None
        return str(media_id)
