"""Bot Framework Connector API client — OAuth + HTTP for MSTeams.

Handles OAuth token lifecycle (client_credentials grant), serviceUrl-based
activity posting, and conversation-scoped serviceUrl caching with TTL eviction.

[INPUT]

[OUTPUT]
- BotFrameworkApi: async API client for Bot Framework Connector REST API

[POS]
Bot Framework HTTP layer. Wraps OAuth token management, serviceUrl caching,
activity POST/PUT/DELETE, providing low-level API capabilities for MSTeamsChannel.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import OrderedDict

import httpx

from app.channels.core.exceptions import ChannelAuthError
from app.channels.types import MediaAttachment

logger = logging.getLogger(__name__)

_SEND_TIMEOUT = 15.0
_TOKEN_REFRESH_BUFFER = 300
_LOGIN_URL = "https://login.microsoftonline.com/botframework.com/oauth2/v2.0/token"
_SERVICE_URL_CACHE_MAX = 500
_SERVICE_URL_CACHE_TTL = 86400.0


class BotFrameworkApi:
    """Async client for Bot Framework Connector REST API.

    Manages OAuth token refresh, serviceUrl resolution, and activity CRUD.
    """

    def __init__(self, app_id: str, app_password: str, http: httpx.AsyncClient) -> None:
        self._app_id = app_id
        self._app_password = app_password
        self._http = http
        self._access_token: str = ""
        self._token_expires_at: float = 0.0
        self._token_lock = asyncio.Lock()
        self._service_url_cache: OrderedDict[str, tuple[str, float]] = OrderedDict()

    @property
    def has_token(self) -> bool:
        return bool(self._access_token)

    # ── OAuth token management ─────────────────────────────────

    async def refresh_token(self) -> None:
        resp = await self._http.post(
            _LOGIN_URL,
            data={
                "grant_type": "client_credentials",
                "client_id": self._app_id,
                "client_secret": self._app_password,
                "scope": "https://api.botframework.com/.default",
            },
            timeout=10.0,
        )
        if resp.status_code != 200:
            raise ChannelAuthError(
                f"MSTeams token refresh failed: HTTP {resp.status_code}",
                channel="teams",
            )
        data = resp.json()
        self._access_token = str(data.get("access_token", ""))
        expire = int(data.get("expires_in", 3600))
        self._token_expires_at = time.monotonic() + expire - _TOKEN_REFRESH_BUFFER

    async def ensure_token(self) -> None:
        if time.monotonic() < self._token_expires_at:
            return
        async with self._token_lock:
            if time.monotonic() >= self._token_expires_at:
                await self.refresh_token()

    # ── serviceUrl cache ───────────────────────────────────────

    def cache_service_url(self, conversation_id: str, service_url: str) -> None:
        now = time.monotonic()
        self._service_url_cache[conversation_id] = (service_url, now)
        self._service_url_cache.move_to_end(conversation_id)
        while len(self._service_url_cache) > _SERVICE_URL_CACHE_MAX:
            self._service_url_cache.popitem(last=False)

    def resolve_service_url(self, conversation_id: str) -> str:
        entry = self._service_url_cache.get(conversation_id)
        if not entry:
            return ""
        url, ts = entry
        if time.monotonic() - ts > _SERVICE_URL_CACHE_TTL:
            self._service_url_cache.pop(conversation_id, None)
            return ""
        return url

    def clear_cache(self) -> None:
        self._service_url_cache.clear()

    # ── Activity CRUD ──────────────────────────────────────────

    def _auth_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._access_token}",
            "Content-Type": "application/json",
        }

    async def post_activity(
        self,
        service_url: str,
        conversation_id: str,
        payload: dict[str, object],
    ) -> str | None:
        if not service_url:
            logger.debug("MSTeams: no service_url, cannot send")
            return None

        await self.ensure_token()
        url = f"{service_url.rstrip('/')}/v3/conversations/{conversation_id}/activities"
        resp = await self._http.post(
            url,
            headers=self._auth_headers(),
            json=payload,
            timeout=_SEND_TIMEOUT,
        )
        if resp.status_code >= 400:
            logger.debug("MSTeams send failed: HTTP %d — %s", resp.status_code, resp.text[:200])
            return None
        try:
            data = resp.json()
        except (ValueError, UnicodeDecodeError):
            logger.debug("MSTeams send: non-JSON response (HTTP %d)", resp.status_code)
            return None
        return str(data.get("id", "")) or None

    async def send_text_activity(
        self,
        service_url: str,
        conversation_id: str,
        text: str,
    ) -> str | None:
        return await self.post_activity(
            service_url,
            conversation_id,
            {"type": "message", "text": text},
        )

    async def send_attachment(
        self,
        service_url: str,
        conversation_id: str,
        media: MediaAttachment,
    ) -> str | None:
        if not service_url or not media.url:
            return None

        payload: dict[str, object] = {
            "type": "message",
            "attachments": [
                {
                    "contentType": media.mime_type or "application/octet-stream",
                    "contentUrl": media.url,
                    "name": media.filename or "file",
                }
            ],
        }
        if media.caption:
            payload["text"] = media.caption

        return await self.post_activity(service_url, conversation_id, payload)

    async def update_activity(
        self,
        service_url: str,
        conversation_id: str,
        activity_id: str,
        payload: dict[str, object],
    ) -> bool:
        await self.ensure_token()
        url = f"{service_url.rstrip('/')}/v3/conversations/{conversation_id}/activities/{activity_id}"
        resp = await self._http.put(
            url,
            headers=self._auth_headers(),
            json=payload,
            timeout=_SEND_TIMEOUT,
        )
        if resp.status_code >= 400:
            logger.debug("MSTeams edit failed: HTTP %d — %s", resp.status_code, resp.text[:200])
            return False
        return True

    async def delete_activity(
        self,
        service_url: str,
        conversation_id: str,
        activity_id: str,
    ) -> bool:
        await self.ensure_token()
        url = f"{service_url.rstrip('/')}/v3/conversations/{conversation_id}/activities/{activity_id}"
        resp = await self._http.delete(
            url,
            headers=self._auth_headers(),
            timeout=_SEND_TIMEOUT,
        )
        if resp.status_code >= 400:
            logger.debug("MSTeams delete failed: HTTP %d — %s", resp.status_code, resp.text[:200])
            return False
        return True

    async def send_typing(
        self,
        service_url: str,
        conversation_id: str,
    ) -> None:
        await self.ensure_token()
        url = f"{service_url.rstrip('/')}/v3/conversations/{conversation_id}/activities"
        await self._http.post(
            url,
            headers=self._auth_headers(),
            json={"type": "typing"},
            timeout=5.0,
        )

    async def add_reaction(
        self,
        service_url: str,
        conversation_id: str,
        activity_id: str,
        reaction_type: str,
    ) -> None:
        await self.ensure_token()
        url = f"{service_url.rstrip('/')}/v3/conversations/{conversation_id}/activities/{activity_id}/reactions"
        await self._http.post(
            url,
            headers=self._auth_headers(),
            json={"type": reaction_type},
            timeout=5.0,
        )
