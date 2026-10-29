"""Slack Web API client — async HTTP wrapper for Bot Token auth.

Covers the subset of Slack Web API methods needed for bidirectional messaging:
auth.test, chat.postMessage, chat.update, chat.delete, reactions.add,
files.getUploadURLExternal + completeUploadExternal (3-step upload),
assistant.threads.setStatus (AI Agent status indicator),
apps.connections.open (Socket Mode).

[INPUT]
- slack.format_converter::neutralize_broadcast_mentions (POS: escapes audience-notifying tokens in the comment that introduces an uploaded file)

[OUTPUT]
- SlackClient: async API client for Slack Web API

[POS]
Slack Web API client. Wraps HTTP calls and error handling,
providing low-level API capabilities for SlackChannel.
"""

from __future__ import annotations

import logging
from typing import NoReturn

import httpx

from app.channels.core.exceptions import (
    ChannelAuthError,
    ChannelSendError,
    RateLimitError,
)
from app.channels.types import MediaAttachment

from .format_converter import neutralize_broadcast_mentions

logger = logging.getLogger(__name__)

_API_BASE = "https://slack.com/api"
_SEND_TIMEOUT = 15.0
# The reaction is already in the state the call asked for.
_SETTLED_REACTION_ERRORS = frozenset({"already_reacted", "no_reaction"})
# chat.postMessage / chat.update answers for blocks Slack will not take; the text can still be delivered.
_BLOCK_ERRORS = frozenset({"invalid_blocks", "invalid_blocks_format", "msg_blocks_too_long"})
_UPLOAD_TIMEOUT = 60.0


class SlackClient:
    """Async client for Slack Web API with Bot Token auth."""

    def __init__(self, bot_token: str, *, app_token: str = "") -> None:
        self._token = bot_token
        self._app_token = app_token
        self._http = httpx.AsyncClient(
            headers={"Authorization": f"Bearer {bot_token}"},
        )

    @property
    def http(self) -> httpx.AsyncClient:
        return self._http

    async def close(self) -> None:
        await self._http.aclose()

    # ── Auth ───────────────────────────────────────────────────

    async def auth_test(self) -> dict[str, str]:
        """Call auth.test and return bot_user_id + team_id."""
        resp = await self._http.post(f"{_API_BASE}/auth.test", timeout=10.0)
        data = resp.json()
        if not data.get("ok"):
            raise ChannelAuthError(f"Slack auth.test failed: {data.get('error')}", channel="slack")
        return {
            "user_id": str(data.get("user_id", "")),
            "team_id": str(data.get("team_id", "")),
        }

    async def health_check(self) -> bool:
        try:
            resp = await self._http.post(f"{_API_BASE}/auth.test", timeout=10.0)
            data = resp.json()
            return bool(data.get("ok"))
        except Exception:
            return False

    async def users_info(self, user_id: str) -> dict[str, object]:
        """Call users.info API to get user details.

        Args:
            user_id: Slack user ID (e.g., U12345)

        Returns:
            User object dict with keys: id, name, profile (display_name, real_name)

        Raises:
            ChannelSendError: API call failed or user not found

        Example:
            user = await client.users_info("U12345")
            name = user.get("profile", {}).get("display_name") or user.get("name")
        """
        resp = await self._http.post(
            f"{_API_BASE}/users.info",
            json={"user": user_id},
            timeout=5.0,
        )
        data = resp.json()
        if not data.get("ok"):
            error = str(data.get("error", "unknown"))
            if error in ("token_revoked", "invalid_auth", "not_authed"):
                raise ChannelAuthError(f"Slack users.info auth error: {error}", channel="slack")
            if error == "ratelimited":
                ra = float(resp.headers.get("Retry-After", "1"))
                raise RateLimitError("Slack rate limited", channel="slack", retry_after=ra)
            raise ChannelSendError(
                f"Slack users.info failed: {error}",
                channel="slack",
                status_code=resp.status_code,
                retriable=error in ("internal_error", "fatal_error", "request_timeout"),
            )
        return dict(data.get("user", {}))

    # ── Messaging ──────────────────────────────────────────────

    async def post_message(self, payload: dict[str, object]) -> str | None:
        """Post a message and return ts. Raises on auth/rate/send errors."""
        data = await self._call_message_method("chat.postMessage", payload, "send")
        ts = data.get("ts")
        return str(ts) if ts else None

    async def update_message(
        self,
        channel: str,
        ts: str,
        text: str,
        blocks: list[dict[str, object]] | None = None,
    ) -> None:
        """Replace a message with ``text`` (or with ``blocks``, ``text`` then being the notification fallback).

        Raises like ``post_message``, so a caller can post the text instead.
        """
        payload: dict[str, object] = {"channel": channel, "ts": ts, "text": text}
        if blocks:
            payload["blocks"] = blocks
        await self._call_message_method("chat.update", payload, "edit")

    async def _call_message_method(self, method: str, payload: dict[str, object], action: str) -> dict[str, object]:
        """Call chat.postMessage / chat.update; blocks Slack refuses are dropped so the text still gets through."""
        resp = await self._http.post(f"{_API_BASE}/{method}", json=payload, timeout=_SEND_TIMEOUT)
        data = resp.json()
        if data.get("ok"):
            return dict(data)
        if payload.get("blocks") and data.get("error") in _BLOCK_ERRORS:
            logger.warning("Slack refused the blocks of a message (%s); %s the text alone", data["error"], action)
            return await self._call_message_method(method, {k: v for k, v in payload.items() if k != "blocks"}, action)
        self._raise_message_error(resp, data, action)

    @staticmethod
    def _raise_message_error(resp: httpx.Response, data: dict[str, object], action: str) -> NoReturn:
        """Raise the typed error for a chat.postMessage / chat.update reply whose ``ok`` is false."""
        error = str(data.get("error", "unknown"))
        if error in ("token_revoked", "invalid_auth", "not_authed"):
            raise ChannelAuthError(f"Slack {action} auth error: {error}", channel="slack")
        if error == "ratelimited":
            retry_after = float(resp.headers.get("Retry-After", "1"))
            raise RateLimitError("Slack rate limited", channel="slack", retry_after=retry_after)
        raise ChannelSendError(
            f"Slack {action} failed: {error}",
            channel="slack",
            status_code=resp.status_code,
            retriable=error in ("internal_error", "fatal_error", "request_timeout"),
        )

    async def delete_message(self, channel: str, ts: str) -> bool:
        payload = {"channel": channel, "ts": ts}
        resp = await self._http.post(f"{_API_BASE}/chat.delete", json=payload, timeout=_SEND_TIMEOUT)
        data = resp.json()
        if not data.get("ok"):
            logger.debug("Slack deleteMessage failed: %s", data.get("error"))
            return False
        return True

    async def add_reaction(self, channel: str, ts: str, emoji_name: str) -> None:
        await self._reaction_call("reactions.add", channel, ts, emoji_name)

    async def remove_reaction(self, channel: str, ts: str, emoji_name: str) -> None:
        await self._reaction_call("reactions.remove", channel, ts, emoji_name)

    async def _reaction_call(self, method: str, channel: str, ts: str, emoji_name: str) -> None:
        """Call a reactions.* method; raises with the missing scope named so a bot without it is diagnosable."""
        payload = {"channel": channel, "timestamp": ts, "name": emoji_name}
        resp = await self._http.post(f"{_API_BASE}/{method}", json=payload, timeout=_SEND_TIMEOUT)
        data = resp.json()
        if data.get("ok"):
            return
        error = str(data.get("error", "unknown"))
        if error in _SETTLED_REACTION_ERRORS:
            return
        needed = f" (needs scope {data['needed']})" if data.get("needed") else ""
        raise ChannelSendError(
            f"Slack {method} failed: {error}{needed}", channel="slack", status_code=resp.status_code, retriable=False
        )

    # ── Assistant Thread Status ─────────────────────────────────

    async def set_thread_status(self, channel_id: str, thread_ts: str, status: str) -> bool:
        """Set assistant thread status via assistant.threads.setStatus.

        Displays a status indicator (e.g. "is thinking...") next to the bot name
        in a thread. Requires chat:write scope (since March 2026).
        Sending an empty status clears the indicator.
        """
        try:
            resp = await self._http.post(
                f"{_API_BASE}/assistant.threads.setStatus",
                json={"channel_id": channel_id, "thread_ts": thread_ts, "status": status},
                timeout=_SEND_TIMEOUT,
            )
            return bool(resp.json().get("ok"))
        except Exception as exc:
            logger.debug("Slack setStatus failed: %s", exc)
            return False

    # ── File Upload (3-step) ───────────────────────────────────

    async def upload_file(
        self,
        channel_id: str,
        attachment: MediaAttachment,
        thread_ts: object | None,
    ) -> bool:
        if not attachment.path and not attachment.url:
            return False
        try:
            if attachment.path:
                with open(attachment.path, "rb") as f:
                    file_bytes = f.read()
            elif attachment.url:
                from app.channels.media import (
                    MAX_FORWARD_DOWNLOAD_BYTES,
                    MediaDownloadConfig,
                    MediaDownloader,
                )

                config = MediaDownloadConfig(
                    timeout_seconds=_UPLOAD_TIMEOUT,
                    max_size_bytes=MAX_FORWARD_DOWNLOAD_BYTES,
                )
                downloader = MediaDownloader(http_client=self._http, enable_default_cache=True)
                result = await downloader.download(attachment.url, config=config)
                if not result.success or not result.data:
                    return False
                file_bytes = result.data
            else:
                return False

            filename = attachment.filename or "file"
            step1 = await self._http.post(
                f"{_API_BASE}/files.getUploadURLExternal",
                data={"filename": filename, "length": str(len(file_bytes))},
                timeout=_SEND_TIMEOUT,
            )
            step1_data = step1.json()
            if not step1_data.get("ok"):
                logger.warning("Slack getUploadURLExternal failed: %s", step1_data.get("error"))
                return False
            upload_url: str = step1_data["upload_url"]
            file_id: str = step1_data["file_id"]

            put_resp = await self._http.put(upload_url, content=file_bytes, timeout=_UPLOAD_TIMEOUT)
            if put_resp.status_code >= 400:
                logger.warning("Slack file PUT failed: HTTP %s", put_resp.status_code)
                return False

            complete_payload: dict[str, object] = {
                "files": [{"id": file_id, "title": filename}],
                "channel_id": channel_id,
            }
            if attachment.caption:
                complete_payload["initial_comment"] = neutralize_broadcast_mentions(attachment.caption)
            if thread_ts:
                complete_payload["thread_ts"] = str(thread_ts)

            step3 = await self._http.post(
                f"{_API_BASE}/files.completeUploadExternal",
                json=complete_payload,
                timeout=_SEND_TIMEOUT,
            )
            step3_data = step3.json()
            if not step3_data.get("ok"):
                logger.warning("Slack completeUploadExternal failed: %s", step3_data.get("error"))
                return False
            return True
        except Exception as exc:
            logger.warning("Slack file upload error: %s", exc)
            return False

    # ── Socket Mode ────────────────────────────────────────────

    async def open_socket_connection(self) -> str:
        """Open a Socket Mode connection and return the WebSocket URL."""
        resp = await self._http.post(
            f"{_API_BASE}/apps.connections.open",
            headers={"Authorization": f"Bearer {self._app_token}"},
            timeout=10.0,
        )
        data = resp.json()
        if not data.get("ok"):
            raise RuntimeError(f"Socket mode connect failed: {data.get('error')}")
        return str(data.get("url", ""))
