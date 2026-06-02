"""Slack Web API client — async HTTP wrapper for Bot Token auth.

Covers the subset of Slack Web API methods needed for bidirectional messaging:
auth.test, chat.postMessage, chat.update, chat.delete, reactions.add,
files.getUploadURLExternal + completeUploadExternal (3-step upload),
chat.startStream / appendStream / stopStream (native AI UX),
assistant.threads.setStatus (AI Agent status indicator),
apps.connections.open (Socket Mode).

[INPUT]

[OUTPUT]
- SlackClient: async API client for Slack Web API

[POS]
Slack Web API client. Wraps HTTP calls and error handling,
providing low-level API capabilities for SlackChannel.
"""

from __future__ import annotations

import logging

import httpx

from app.channels.core.exceptions import (
    ChannelAuthError,
    ChannelSendError,
    RateLimitError,
)
from app.channels.types import MediaAttachment

logger = logging.getLogger(__name__)

_API_BASE = "https://slack.com/api"
_SEND_TIMEOUT = 15.0
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
        resp = await self._http.post(
            f"{_API_BASE}/chat.postMessage",
            json=payload,
            timeout=_SEND_TIMEOUT,
        )
        data = resp.json()
        if not data.get("ok"):
            error = str(data.get("error", "unknown"))
            if error in ("token_revoked", "invalid_auth", "not_authed"):
                raise ChannelAuthError(f"Slack send auth error: {error}", channel="slack")
            if error == "ratelimited":
                ra = float(resp.headers.get("Retry-After", "1"))
                raise RateLimitError("Slack rate limited", channel="slack", retry_after=ra)
            raise ChannelSendError(
                f"Slack send failed: {error}",
                channel="slack",
                status_code=resp.status_code,
                retriable=error in ("internal_error", "fatal_error", "request_timeout"),
            )
        ts = data.get("ts")
        return str(ts) if ts else None

    async def update_message(self, channel: str, ts: str, text: str) -> bool:
        payload: dict[str, object] = {"channel": channel, "ts": ts, "text": text}
        resp = await self._http.post(f"{_API_BASE}/chat.update", json=payload, timeout=_SEND_TIMEOUT)
        data = resp.json()
        if not data.get("ok"):
            logger.debug("Slack editMessage failed: %s", data.get("error"))
            return False
        return True

    async def delete_message(self, channel: str, ts: str) -> bool:
        payload = {"channel": channel, "ts": ts}
        resp = await self._http.post(f"{_API_BASE}/chat.delete", json=payload, timeout=_SEND_TIMEOUT)
        data = resp.json()
        if not data.get("ok"):
            logger.debug("Slack deleteMessage failed: %s", data.get("error"))
            return False
        return True

    async def add_reaction(self, channel: str, ts: str, emoji_name: str) -> bool:
        payload = {"channel": channel, "timestamp": ts, "name": emoji_name}
        resp = await self._http.post(f"{_API_BASE}/reactions.add", json=payload, timeout=_SEND_TIMEOUT)
        data = resp.json()
        if not data.get("ok"):
            logger.debug("Slack react failed: %s", data.get("error"))
            return False
        return True

    # ── Streaming ──────────────────────────────────────────────

    async def start_stream(self, channel: str, thread_ts: str, text: str, team_id: str = "") -> str | None:
        payload: dict[str, object] = {
            "channel": channel,
            "thread_ts": thread_ts,
        }
        if text:
            payload["markdown_text"] = text
        if team_id:
            payload["recipient_team_id"] = team_id
        try:
            resp = await self._http.post(
                f"{_API_BASE}/chat.startStream",
                json=payload,
                timeout=_SEND_TIMEOUT,
            )
            data = resp.json()
            if data.get("ok"):
                ts = str(data.get("ts", ""))
                return ts or None
            logger.debug("Slack startStream failed: %s", data.get("error"))
        except Exception as exc:
            logger.debug("Slack startStream error: %s", exc)
        return None

    async def append_stream(self, channel: str, ts: str, text: str) -> bool:
        try:
            resp = await self._http.post(
                f"{_API_BASE}/chat.appendStream",
                json={"channel": channel, "ts": ts, "markdown_text": text},
                timeout=_SEND_TIMEOUT,
            )
            data = resp.json()
            if data.get("ok"):
                return True
            logger.debug("Slack appendStream failed: %s", data.get("error"))
        except Exception as exc:
            logger.debug("Slack appendStream error: %s", exc)
        return False

    async def stop_stream(self, channel: str, ts: str, payload: dict[str, object]) -> bool:
        try:
            resp = await self._http.post(
                f"{_API_BASE}/chat.stopStream",
                json=payload,
                timeout=_SEND_TIMEOUT,
            )
            data = resp.json()
            if data.get("ok"):
                return True
            logger.debug("Slack stopStream failed: %s", data.get("error"))
        except Exception as exc:
            logger.debug("Slack stopStream error: %s", exc)
        return False

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
                    MediaDownloadConfig,
                    MediaDownloader,
                )

                config = MediaDownloadConfig(timeout_seconds=_UPLOAD_TIMEOUT)
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
                complete_payload["initial_comment"] = attachment.caption
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
