"""Signal CLI REST API client (HTTP + WebSocket).

Encapsulates all interactions with the Signal CLI REST API:
messaging, typing indicators, reactions, groups, health check,
WebSocket real-time receiving, and HTTP polling fallback.

[INPUT]
- .helpers::constants, TypedDict structures (POS: Signal envelope type definitions and pure functions.)

[OUTPUT]
- SignalClient: HTTP + WebSocket client for Signal CLI REST API

[POS]
Signal HTTP/WS layer. Provides REST messaging, WebSocket stream_events(), and HTTP polling fallback. Called by channel.py via self._api.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncGenerator

import httpx

from app.channels.providers.signal.helpers import (
    _HEALTH_TIMEOUT,
    _POLL_INTERVAL,
    _SEND_TIMEOUT,
    _TYPING_TIMEOUT,
    _WS_PING_INTERVAL,
    _WS_PING_TIMEOUT,
)

logger = logging.getLogger(__name__)


class SignalClient:
    """HTTP + WebSocket client for Signal CLI REST API."""

    def __init__(self, api_url: str, phone_number: str) -> None:
        self._api_url = api_url.rstrip("/")
        self._phone = phone_number
        self._http = httpx.AsyncClient()

    @property
    def ws_url(self) -> str:
        base = self._api_url.replace("https://", "wss://").replace("http://", "ws://")
        return f"{base}/v1/receive/{self._phone}"

    async def close(self) -> None:
        await self._http.aclose()

    # ── Health ────────────────────────────────────────────────────────

    async def health_check(self) -> tuple[bool, str]:
        """Check API health. Returns (ok, error_message)."""
        resp = await self._http.get(
            f"{self._api_url}/v1/about",
            timeout=_HEALTH_TIMEOUT,
        )
        if resp.status_code == 200:
            return True, ""
        return False, f"HTTP {resp.status_code}"

    # ── Groups ────────────────────────────────────────────────────────

    async def list_groups(self) -> list[dict[str, str]]:
        """Fetch groups list. Returns raw group dicts."""
        resp = await self._http.get(
            f"{self._api_url}/v1/groups/{self._phone}",
            timeout=_HEALTH_TIMEOUT,
        )
        if resp.status_code != 200:
            return []
        data = resp.json()
        return data if isinstance(data, list) else []

    # ── Messaging ─────────────────────────────────────────────────────

    async def send_message(
        self,
        payload: dict[str, str | list[str]],
    ) -> httpx.Response:
        """Send a message via /v2/send."""
        return await self._http.post(
            f"{self._api_url}/v2/send",
            json=payload,
            timeout=_SEND_TIMEOUT,
        )

    # ── Typing ────────────────────────────────────────────────────────

    async def start_typing(self, chat_id: str) -> None:
        await self._http.put(
            f"{self._api_url}/v1/typing-indicator/{self._phone}",
            json={"recipient": chat_id},
            timeout=_TYPING_TIMEOUT,
        )

    async def stop_typing(self) -> None:
        await self._http.delete(
            f"{self._api_url}/v1/typing-indicator/{self._phone}",
            timeout=_TYPING_TIMEOUT,
        )

    # ── Reactions ─────────────────────────────────────────────────────

    async def send_reaction(
        self,
        chat_id: str,
        emoji: str,
        target_author: str,
        timestamp: int,
    ) -> None:
        payload = {
            "recipient": chat_id,
            "reaction": {
                "emoji": emoji,
                "target_author": target_author,
                "timestamp": timestamp,
            },
        }
        await self._http.post(
            f"{self._api_url}/v1/reactions/{self._phone}",
            json=payload,
            timeout=_SEND_TIMEOUT,
        )

    # ── WebSocket ─────────────────────────────────────────────────────

    async def stream_events(self) -> AsyncGenerator[dict[str, object]]:
        """Connect to WebSocket and yield parsed envelope dicts.

        Raises on connection failure or server close.
        Caller should wrap in reconnect_loop for auto-reconnect.
        """
        from websockets.asyncio.client import connect

        async with connect(
            self.ws_url,
            ping_interval=_WS_PING_INTERVAL,
            ping_timeout=_WS_PING_TIMEOUT,
            close_timeout=5,
        ) as ws:
            async for raw in ws:
                if isinstance(raw, bytes):
                    raw = raw.decode("utf-8", errors="replace")
                try:
                    payload: dict[str, object] = json.loads(raw)
                    yield payload
                except json.JSONDecodeError:
                    logger.debug("Signal WS: invalid JSON: %s", raw[:200])

    # ── Polling (fallback) ────────────────────────────────────────────

    async def receive(self) -> list[dict[str, object]]:
        """Poll for new messages. Returns list of envelope payloads."""
        resp = await self._http.get(
            f"{self._api_url}/v1/receive/{self._phone}",
            timeout=_POLL_INTERVAL + 5,
        )
        if resp.status_code != 200:
            return []
        data = resp.json()
        return data if isinstance(data, list) else []

    # ── Media download ────────────────────────────────────────────────

    async def download_attachment(self, attachment_id: str) -> bytes | None:
        """Download an attachment by ID. Returns raw bytes or None."""
        resp = await self._http.get(
            f"{self._api_url}/v1/attachments/{attachment_id}",
            timeout=_SEND_TIMEOUT,
        )
        if resp.status_code == 200:
            return resp.content
        return None
