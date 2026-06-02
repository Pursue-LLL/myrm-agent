"""Mattermost REST API v4 client — Bot Access Token auth.

Provides async methods for posts, reactions, files, and channels.
WebSocket event streaming via ``stream_events()``.

[INPUT]
- (none)

[OUTPUT]
- MattermostClient: Async client for Mattermost REST API v4.

[POS]
app.channels.providers.mattermost.api — Mattermost REST API v4 client with Bot Access Token auth.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncGenerator

import httpx

from .._http_timeout import resolve_timeout

logger = logging.getLogger(__name__)

_TIMEOUT = resolve_timeout(15.0)


class MattermostClient:
    """Async client for Mattermost REST API v4.

    Authenticates using a Bot Personal Access Token.
    Manages lazy-initialized httpx.AsyncClient for REST
    and websockets connection for real-time events.
    """

    def __init__(self, server_url: str, access_token: str) -> None:
        self._server_url = server_url.rstrip("/")
        self._access_token = access_token
        self._http: httpx.AsyncClient | None = None
        self._bot_user_id: str = ""

    @property
    def is_configured(self) -> bool:
        return bool(self._server_url and self._access_token)

    @property
    def api_url(self) -> str:
        return f"{self._server_url}/api/v4"

    @property
    def ws_url(self) -> str:
        base = self._server_url.replace("https://", "wss://").replace("http://", "ws://")
        return f"{base}/api/v4/websocket"

    @property
    def bot_user_id(self) -> str:
        return self._bot_user_id

    def _get_http(self) -> httpx.AsyncClient:
        if self._http is None or self._http.is_closed:
            self._http = httpx.AsyncClient(
                timeout=_TIMEOUT,
                headers={
                    "Authorization": f"Bearer {self._access_token}",
                    "Content-Type": "application/json",
                },
            )
        return self._http

    async def close(self) -> None:
        if self._http and not self._http.is_closed:
            await self._http.aclose()
            self._http = None

    # ── Authentication & User ──────────────────────────────────────

    async def get_me(self) -> dict[str, object]:
        """GET /users/me — verify token and get bot user info."""
        resp = await self._get_http().get(f"{self.api_url}/users/me")
        resp.raise_for_status()
        data: dict[str, object] = resp.json()
        user_id = data.get("id", "")
        if isinstance(user_id, str) and user_id:
            self._bot_user_id = user_id
        return data

    # ── Posts ──────────────────────────────────────────────────────

    async def create_post(
        self,
        channel_id: str,
        message: str,
        *,
        root_id: str = "",
        file_ids: list[str] | None = None,
    ) -> dict[str, object]:
        """POST /posts — create a message in a channel."""
        body: dict[str, object] = {
            "channel_id": channel_id,
            "message": message,
        }
        if root_id:
            body["root_id"] = root_id
        if file_ids:
            body["file_ids"] = file_ids

        resp = await self._get_http().post(f"{self.api_url}/posts", json=body)
        resp.raise_for_status()
        return resp.json()

    async def update_post(self, post_id: str, message: str) -> dict[str, object]:
        """PUT /posts/{post_id} — edit message content."""
        resp = await self._get_http().put(
            f"{self.api_url}/posts/{post_id}",
            json={"id": post_id, "message": message},
        )
        resp.raise_for_status()
        return resp.json()

    async def delete_post(self, post_id: str) -> None:
        """DELETE /posts/{post_id} — soft-delete a post."""
        resp = await self._get_http().delete(f"{self.api_url}/posts/{post_id}")
        resp.raise_for_status()

    # ── Reactions ──────────────────────────────────────────────────

    async def add_reaction(self, user_id: str, post_id: str, emoji_name: str) -> None:
        """POST /reactions — add emoji reaction to a post."""
        resp = await self._get_http().post(
            f"{self.api_url}/reactions",
            json={
                "user_id": user_id,
                "post_id": post_id,
                "emoji_name": emoji_name,
            },
        )
        resp.raise_for_status()

    # ── Files ─────────────────────────────────────────────────────

    async def upload_file(
        self,
        channel_id: str,
        filename: str,
        data: bytes,
    ) -> str:
        """POST /files — upload file attachment, return file_id."""
        http = self._get_http()
        resp = await http.post(
            f"{self.api_url}/files",
            data={"channel_id": channel_id},
            files={"files": (filename, data)},
        )
        resp.raise_for_status()
        result: dict[str, object] = resp.json()
        file_infos = result.get("file_infos", [])
        if isinstance(file_infos, list) and file_infos:
            first = file_infos[0]
            if isinstance(first, dict):
                fid = first.get("id", "")
                if isinstance(fid, str):
                    return fid
        return ""

    # ── Channels ──────────────────────────────────────────────────

    async def get_channels_for_user(self, user_id: str, team_id: str) -> list[dict[str, object]]:
        """GET /users/{user_id}/teams/{team_id}/channels."""
        resp = await self._get_http().get(
            f"{self.api_url}/users/{user_id}/teams/{team_id}/channels",
        )
        resp.raise_for_status()
        result: list[dict[str, object]] = resp.json()
        return result

    async def get_teams_for_user(self, user_id: str) -> list[dict[str, object]]:
        """GET /users/{user_id}/teams."""
        resp = await self._get_http().get(f"{self.api_url}/users/{user_id}/teams")
        resp.raise_for_status()
        result: list[dict[str, object]] = resp.json()
        return result

    # ── WebSocket ──────────────────────────────────────────────────

    async def stream_events(self) -> AsyncGenerator[dict[str, object]]:
        """Connect to WebSocket and yield parsed event dicts.

        Raises on connection failure or server close.
        Caller should wrap in reconnect_loop for auto-reconnect.
        """
        from websockets.asyncio.client import connect

        async with connect(
            self.ws_url,
            additional_headers={"Authorization": f"Bearer {self._access_token}"},
            ping_interval=30,
            ping_timeout=10,
            close_timeout=5,
        ) as ws:
            auth_msg = json.dumps(
                {
                    "seq": 1,
                    "action": "authentication_challenge",
                    "data": {"token": self._access_token},
                }
            )
            await ws.send(auth_msg)

            async for raw in ws:
                if isinstance(raw, bytes):
                    raw = raw.decode("utf-8", errors="replace")
                try:
                    event: dict[str, object] = json.loads(raw)
                    yield event
                except json.JSONDecodeError:
                    logger.debug("Mattermost WS: invalid JSON: %s", raw[:200])
