"""LINE Messaging API HTTP client.

Encapsulates all HTTP interactions with the LINE Messaging API:
reply/push messaging, bot info, health check, typing indicator.

[INPUT]
- .helpers::_API_BASE, (POS: Stateless helper functions extracted from orchestrator.py to keep the main orchestrator class focused on state machine logic.)

[OUTPUT]
- LineClient: stateless HTTP wrapper for LINE Messaging API

[POS]
LINE HTTP layer. Called by channel.py via self._api.
"""

from __future__ import annotations

import logging

import httpx

from app.channels.providers.line.helpers import (
    _API_BASE,
    _HEALTH_TIMEOUT,
    _LOADING_TIMEOUT,
    _SEND_TIMEOUT,
)

logger = logging.getLogger(__name__)


class LineClient:
    """HTTP client for LINE Messaging API."""

    def __init__(self, channel_access_token: str) -> None:
        self._token = channel_access_token
        self._http = httpx.AsyncClient(
            headers={"Authorization": f"Bearer {channel_access_token}"},
        )

    async def close(self) -> None:
        await self._http.aclose()

    async def get_bot_info(self) -> dict[str, str]:
        """Fetch bot profile info. Returns dict with userId, displayName."""
        resp = await self._http.get(f"{_API_BASE}/info", timeout=_HEALTH_TIMEOUT)
        if resp.status_code == 200:
            data = resp.json()
            return {
                "userId": data.get("userId", ""),
                "displayName": data.get("displayName", ""),
            }
        return {}

    async def health_check(self) -> tuple[bool, str]:
        """Check API health. Returns (ok, error_message)."""
        resp = await self._http.get(f"{_API_BASE}/info", timeout=_HEALTH_TIMEOUT)
        if resp.status_code == 200:
            return True, ""
        return False, f"Bot Info API returned {resp.status_code}"

    async def reply(
        self,
        reply_token: str,
        messages: list[dict[str, object]],
    ) -> httpx.Response:
        """Send reply message (free, uses reply token)."""
        payload: dict[str, object] = {
            "replyToken": reply_token,
            "messages": messages,
        }
        return await self._http.post(
            f"{_API_BASE}/message/reply",
            json=payload,
            timeout=_SEND_TIMEOUT,
        )

    async def push(
        self,
        to: str,
        messages: list[dict[str, object]],
    ) -> httpx.Response:
        """Send push message (paid, no reply token needed)."""
        payload: dict[str, object] = {"to": to, "messages": messages}
        return await self._http.post(
            f"{_API_BASE}/message/push",
            json=payload,
            timeout=_SEND_TIMEOUT,
        )

    async def start_loading(self, chat_id: str) -> None:
        """Show typing/loading animation for a 1:1 chat."""
        if not chat_id or chat_id.startswith(("C", "R")):
            return
        try:
            await self._http.post(
                f"{_API_BASE}/chat/loading/start",
                json={"chatId": chat_id, "loadingSeconds": 60},
                timeout=_LOADING_TIMEOUT,
            )
        except Exception:
            pass
