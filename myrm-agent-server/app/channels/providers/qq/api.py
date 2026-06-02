"""QQ Bot Official API HTTP client.

Encapsulates OAuth token management and all REST API interactions:
text/media messaging, typing indicator, health check.

[INPUT]
- .helpers::build_message_url, (POS: Stateless helper functions extracted from orchestrator.py to keep the main orchestrator class focused on state machine logic.)

[OUTPUT]
- QQClient: HTTP wrapper for QQ Bot Official API

[POS]
QQ HTTP layer. Called by channel.py via self._api.
"""

from __future__ import annotations

import asyncio
import logging
import time

import httpx

from app.channels.core.exceptions import (
    ChannelAuthError,
    ChannelSendError,
)
from app.channels.providers.qq.helpers import (
    build_media_upload_url,
    build_message_url,
    qq_file_type,
)
from app.channels.types import MediaAttachment

logger = logging.getLogger(__name__)

_TOKEN_URL = "https://bots.qq.com/app/getAppAccessToken"
_SEND_TIMEOUT = 15.0
_TOKEN_REFRESH_BUFFER = 300


class QQClient:
    """HTTP client for QQ Bot Official API with OAuth token management."""

    def __init__(self, app_id: str, client_secret: str, api_base: str) -> None:
        self._app_id = app_id
        self._client_secret = client_secret
        self._api_base = api_base
        self._http = httpx.AsyncClient()
        self._access_token: str = ""
        self._token_expires_at: float = 0.0
        self._token_lock = asyncio.Lock()

    async def close(self) -> None:
        await self._http.aclose()

    # ── Token Management ──────────────────────────────────────────────

    async def refresh_token(self) -> None:
        resp = await self._http.post(
            _TOKEN_URL,
            json={"appId": self._app_id, "clientSecret": self._client_secret},
            timeout=10.0,
        )
        if resp.status_code != 200:
            raise ChannelAuthError(
                f"QQ token refresh failed: HTTP {resp.status_code}",
                channel="qq",
            )
        data = resp.json()
        self._access_token = str(data.get("access_token", ""))
        expire = int(data.get("expires_in", 7200))
        self._token_expires_at = time.monotonic() + expire - _TOKEN_REFRESH_BUFFER

    async def ensure_token(self) -> None:
        if time.monotonic() >= self._token_expires_at:
            async with self._token_lock:
                if time.monotonic() >= self._token_expires_at:
                    await self.refresh_token()

    def auth_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"QQBot {self._access_token}",
            "Content-Type": "application/json",
        }

    # ── Health ────────────────────────────────────────────────────────

    async def health_check(self) -> bool:
        await self.ensure_token()
        resp = await self._http.get(
            f"{self._api_base}/users/@me",
            headers=self.auth_headers(),
            timeout=10.0,
        )
        return resp.status_code == 200

    # ── Gateway ───────────────────────────────────────────────────────

    async def get_gateway_url(self) -> str:
        """Fetch WebSocket gateway URL from QQ API."""
        resp = await self._http.get(
            f"{self._api_base}/gateway",
            headers=self.auth_headers(),
            timeout=10.0,
        )
        return str(resp.json().get("url", ""))

    # ── Messaging ─────────────────────────────────────────────────────

    async def send_text(
        self,
        target_id: str,
        text: str,
        chat_type: str,
        msg_id: str | None,
        msg_seq: int,
    ) -> str | None:
        url = build_message_url(self._api_base, target_id, chat_type)
        payload: dict[str, object] = {
            "content": text,
            "msg_type": 0,
            "msg_seq": msg_seq,
        }
        if msg_id:
            payload["msg_id"] = msg_id

        try:
            resp = await self._http.post(
                url,
                headers=self.auth_headers(),
                json=payload,
                timeout=_SEND_TIMEOUT,
            )
        except Exception as exc:
            raise ChannelSendError(str(exc), channel="qq") from exc

        if resp.status_code >= 400:
            logger.warning("QQ send failed: HTTP %d, body=%s", resp.status_code, resp.text[:200])
            return None
        return str(resp.json().get("id", "")) or None

    async def send_media(
        self,
        target_id: str,
        attachment: MediaAttachment,
        chat_type: str,
        msg_id: str | None,
        msg_seq: int,
    ) -> str | None:
        """Upload media via 2-step flow: upload to /files → send msg_type=7."""
        media_url = attachment.url
        if not media_url:
            return None

        upload_url = build_media_upload_url(self._api_base, target_id, chat_type)
        file_type = qq_file_type(attachment)
        upload_payload: dict[str, object] = {
            "file_type": file_type,
            "url": media_url,
            "srv_send_msg": False,
        }

        try:
            resp = await self._http.post(
                upload_url,
                headers=self.auth_headers(),
                json=upload_payload,
                timeout=30.0,
            )
        except Exception as exc:
            logger.warning("QQ media upload failed: %s", exc)
            return None

        if resp.status_code >= 400:
            logger.warning("QQ media upload HTTP %d: %s", resp.status_code, resp.text[:200])
            return None

        file_info = resp.json().get("file_info")
        if not file_info:
            logger.warning("QQ media upload returned no file_info")
            return None

        send_url = build_message_url(self._api_base, target_id, chat_type)
        send_payload: dict[str, object] = {
            "msg_type": 7,
            "media": {"file_info": file_info},
            "msg_seq": msg_seq,
        }
        if msg_id:
            send_payload["msg_id"] = msg_id

        try:
            resp = await self._http.post(
                send_url,
                headers=self.auth_headers(),
                json=send_payload,
                timeout=_SEND_TIMEOUT,
            )
        except Exception as exc:
            logger.warning("QQ media send failed: %s", exc)
            return None

        if resp.status_code >= 400:
            logger.warning("QQ media send HTTP %d: %s", resp.status_code, resp.text[:200])
            return None
        return str(resp.json().get("id", "")) or None

    async def send_typing(
        self,
        target_id: str,
        chat_type: str,
        msg_id: str,
        msg_seq: int,
    ) -> None:
        """Send QQ InputNotify (msg_type=6) typing indicator."""
        url = build_message_url(self._api_base, target_id, chat_type)
        payload: dict[str, object] = {
            "msg_type": 6,
            "msg_id": msg_id,
            "msg_seq": msg_seq,
        }
        try:
            await self._http.post(
                url,
                headers=self.auth_headers(),
                json=payload,
                timeout=5.0,
            )
        except Exception:
            pass
