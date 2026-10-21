"""Mattermost channel — WebSocket inbound + REST API v4 outbound.

Inbound: WebSocket real-time events (posted).
Outbound: REST API v4 with Bot Personal Access Token auth.

Supports DM and public/private channels, message editing/deletion,
thread replies, emoji reactions, file upload, @mention detection,
and inbound media attachment parsing.

[INPUT]
- app.channels.core.base::BaseChannel (POS: Channel base class with unified send/receive contract.)
- app.channels.types::ChannelCapabilities (POS: Channel capability and artifact type definitions.)
- app.channels.media::MediaDownloadConfig (POS: Media download cache with LRU eviction.)
- app.channels.core.exceptions::ChannelSendError (POS: Channel exception hierarchy.)
- app.channels.core.attachment_delivery::attempt_attachments (POS: per-attachment delivery with aggregated failure)
- app.channels.core.mixins::CachedGroupMixin (POS: Reusable channel capability mixin components.)
- app.channels.providers.mattermost.inbound::MattermostInboundMixin (POS: WebSocket event parsing and inbound media)

[OUTPUT]
- MattermostChannel: Mattermost bidirectional channel (credentials, lifecycle, REST API v4 outbound, groups, diagnostics); WebSocket inbound comes from the mixin.

[POS]
app.channels.providers.mattermost.channel — Mattermost WebSocket inbound + REST API v4 outbound.
"""

from __future__ import annotations

import asyncio
import logging
from functools import partial
from pathlib import Path

import httpx

from app.channels import BaseChannel, OutboundMessage
from app.channels.core.attachment_delivery import attempt_attachments
from app.channels.core.credentials import credential_field, credential_spec
from app.channels.core.exceptions import ChannelSendError
from app.channels.core.mixins import CachedGroupMixin
from app.channels.reliability.reconnect import reconnect_loop
from app.channels.rendering.renderer import render
from app.channels.types import (
    ChannelCapabilities,
    ChannelIssue,
    ChannelStatus,
    GroupInfo,
    IssueKind,
    IssueSeverity,
    MediaAttachment,
    RenderStyle,
    ToolSummaryDisplay,
)

from .api import MattermostClient
from .inbound import MattermostInboundMixin

logger = logging.getLogger(__name__)

_MAX_MSG_LENGTH = 16383


class MattermostChannel(MattermostInboundMixin, BaseChannel, CachedGroupMixin):
    """Mattermost channel using WebSocket inbound + REST API v4 outbound.

    Inbound: WebSocket real-time events (posted).
    Outbound: REST API v4 via Bot Personal Access Token.
    """

    name = "mattermost"
    credential_spec = credential_spec(
        "mattermostCredentials",
        server_url=credential_field("serverUrl", "MATTERMOST_SERVER_URL"),
        access_token=credential_field("accessToken", "MATTERMOST_ACCESS_TOKEN"),
    )
    capabilities = ChannelCapabilities(
        text=True,
        markdown=True,
        media=True,
        buttons=False,
        threads=True,
        edit=True,
        delete=True,
        reactions=True,
        max_text_length=_MAX_MSG_LENGTH,
    )
    render_style = RenderStyle(
        format="markdown",
        max_text_length=_MAX_MSG_LENGTH,
        supports_code_fence=True,
        supports_links=True,
        supports_tables=True,
        tool_summary_display=ToolSummaryDisplay.COMPACT,
    )

    def __init__(self, server_url: str, access_token: str, groups_cache_ttl: float = 300.0) -> None:
        BaseChannel.__init__(self)
        CachedGroupMixin.__init__(self, groups_cache_ttl=groups_cache_ttl)
        self._api = MattermostClient(server_url, access_token)
        self._ws_task: asyncio.Task[None] | None = None
        self._bot_name: str = ""

    async def start(self) -> None:
        if not self._api.is_configured:
            logger.debug("Mattermost: not configured; channel idle")
            return

        try:
            me = await self._api.get_me()
            await super().start()
            self._bot_id = self._api.bot_user_id
            username = me.get("username", "")
            if isinstance(username, str):
                self._bot_name = username
            logger.info("Mattermost: authenticated as bot %s (@%s)", self._bot_id, self._bot_name)
            self._ws_task = asyncio.create_task(
                reconnect_loop(
                    self._ws_connect,
                    lambda: self._status,
                    channel_name="Mattermost",
                ),
            )
        except Exception as exc:
            self._status = ChannelStatus.DEGRADED
            logger.warning("Mattermost: auth failed: %s", exc)

    async def stop(self) -> None:
        if self._ws_task and not self._ws_task.done():
            self._ws_task.cancel()
            try:
                await self._ws_task
            except asyncio.CancelledError:
                pass
            self._ws_task = None
        await self._api.close()
        await super().stop()

    # ── Outbound ──────────────────────────────────────────────────

    async def send(self, msg: OutboundMessage) -> str | None:
        """Post the message; uploaded files ride with its first post.

        A file that cannot be uploaded is reported after the post went out, so the bus republishes only
        that file instead of replaying the whole message.
        """
        channel_id = msg.recipient_id
        if not channel_id:
            raise ChannelSendError("Mattermost message has no channel", channel=self.name, retriable=False)
        if not msg.content and not msg.media:
            return None

        root_id = msg.reply_to_id or ""
        if not root_id and msg.metadata and isinstance(msg.metadata, dict):
            root_id = str(msg.metadata.get("thread_id", "")) or ""

        last_id: str | None = None
        try:
            uploads = await attempt_attachments(self.name, msg.media, partial(self._upload_attachment, channel_id))
            file_ids = list(uploads.results)
            chunks = list(render(msg, self.render_style)) if msg.content else []
            if file_ids and not chunks:
                chunks = [""]  # a files-only message is one post that only carries the files

            for chunk in chunks:
                result = await self._api.create_post(
                    channel_id,
                    chunk,
                    root_id=root_id,
                    file_ids=file_ids if file_ids and last_id is None else None,
                )
                pid = result.get("id")
                if isinstance(pid, str) and pid:
                    last_id = pid
            self.health.record_success()
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            self.health.record_failure(f"HTTP {status}")
            raise ChannelSendError(
                f"Mattermost send failed: HTTP {status}",
                channel=self.name,
                status_code=status,
                retriable=status >= 500 or status == 429,
            ) from exc
        except Exception as exc:
            self.health.record_failure(str(exc))
            raise ChannelSendError(
                f"Mattermost send failed: {exc}",
                channel=self.name,
            ) from exc

        uploads.raise_for_failures(self.name, delivered_any=last_id is not None)
        return last_id

    async def _upload_attachment(self, channel_id: str, attachment: MediaAttachment) -> str:
        """Upload one attachment and return its file id; raises ``ChannelSendError`` when Mattermost does not take it."""
        if attachment.path:
            path = Path(attachment.path)
            try:
                data = await asyncio.to_thread(path.read_bytes)
            except OSError as exc:
                raise ChannelSendError(
                    f"Mattermost cannot read {attachment.display_name}", channel=self.name, retriable=False
                ) from exc
            filename = attachment.filename or path.name
        elif attachment.url:
            data = await self._download_attachment(attachment)
            filename = attachment.filename or "file"
        else:
            raise ChannelSendError(f"Mattermost has no source for {attachment.display_name}", channel=self.name, retriable=False)

        try:
            file_id = await self._api.upload_file(channel_id, filename, data)
        except httpx.HTTPStatusError as exc:
            raise ChannelSendError.from_http_status(self.name, exc.response.status_code, "file upload") from exc
        except httpx.HTTPError as exc:
            raise ChannelSendError(f"Mattermost upload failed: {type(exc).__name__}", channel=self.name) from exc
        if not file_id:
            raise ChannelSendError(f"Mattermost returned no file id for {attachment.display_name}", channel=self.name)
        return file_id

    async def _download_attachment(self, attachment: MediaAttachment) -> bytes:
        """Fetch a remote attachment so it can be uploaded to Mattermost."""
        from app.channels.media import (
            MAX_FORWARD_DOWNLOAD_BYTES,
            MediaDownloadConfig,
            MediaDownloader,
        )

        config = MediaDownloadConfig(timeout_seconds=30.0, max_size_bytes=MAX_FORWARD_DOWNLOAD_BYTES)
        downloader = MediaDownloader(http_client=self._api._get_http(), enable_default_cache=True)
        result = await downloader.download(attachment.url or "", config=config)
        if not result.success or not result.data:
            raise ChannelSendError(f"Mattermost could not download {attachment.display_name}", channel=self.name)
        return result.data

    async def send_placeholder(
        self,
        chat_id: str,
        text: str,
        *,
        thread_id: str | None = None,
    ) -> str | None:
        try:
            result = await self._api.create_post(chat_id, text, root_id=thread_id or "")
            pid = result.get("id")
            return str(pid) if pid else None
        except Exception as exc:
            logger.warning("Mattermost placeholder failed: %s", exc)
            return None

    async def edit_message(self, chat_id: str, message_id: str, text: str) -> None:
        try:
            await self._api.update_post(message_id, text)
        except Exception as exc:
            logger.warning("Mattermost edit failed: %s", exc)

    async def delete_message(self, chat_id: str, message_id: str) -> None:
        try:
            await self._api.delete_post(message_id)
        except Exception as exc:
            logger.warning("Mattermost delete failed: %s", exc)

    async def react_to_message(self, chat_id: str, message_id: str, emoji: str) -> None:
        if not emoji or not self._bot_id:
            return
        emoji_name = emoji.strip().strip(":").replace("", "")
        if not emoji_name:
            return
        try:
            await self._api.add_reaction(self._bot_id, message_id, emoji_name)
        except Exception as exc:
            logger.debug("Mattermost react failed: %s", exc)

    # ── Groups / Channels ─────────────────────────────────────────

    async def list_groups(self, force_refresh: bool = False) -> list[GroupInfo]:
        if not self._api.bot_user_id:
            return []
        if self._is_groups_cache_valid(force_refresh):
            return self._groups_cache.copy()
        try:
            teams = await self._api.get_teams_for_user(self._api.bot_user_id)
            groups: list[GroupInfo] = []
            for team in teams:
                team_id = str(team.get("id", ""))
                if not team_id:
                    continue
                channels = await self._api.get_channels_for_user(self._api.bot_user_id, team_id)
                for ch in channels:
                    ch_type = str(ch.get("type", ""))
                    if ch_type in ("O", "P", "G"):
                        groups.append(
                            GroupInfo(
                                jid=str(ch.get("id", "")),
                                name=str(ch.get("display_name", "") or ch.get("name", "")),
                                channel=self.name,
                            )
                        )
            self._update_groups_cache(groups)
            return groups
        except Exception as exc:
            logger.debug("Mattermost list_groups failed: %s", exc)
            return []

    # ── Health ────────────────────────────────────────────────────

    async def health_check(self) -> bool:
        if not self._api.is_configured:
            return False
        try:
            await self._api.get_me()
            self.health.record_success()
            return True
        except Exception as exc:
            self.health.record_failure(str(exc))
            return False

    def collect_issues(self) -> list[ChannelIssue]:
        issues: list[ChannelIssue] = []
        if not self._api.is_configured:
            missing: list[str] = []
            if not self._api._server_url:
                missing.append("server_url")
            if not self._api._access_token:
                missing.append("access_token")
            issues.append(
                ChannelIssue(
                    kind=IssueKind.CONFIG,
                    severity=IssueSeverity.ERROR,
                    message=f"Missing configuration: {', '.join(missing)}.",
                    fix="Set MATTERMOST_SERVER_URL and MATTERMOST_ACCESS_TOKEN.",
                ),
            )
            return issues
        if self._status == ChannelStatus.DEGRADED:
            issues.append(
                ChannelIssue(
                    kind=IssueKind.CONFIG,
                    severity=IssueSeverity.WARNING,
                    message="Authentication failed. Channel running in degraded mode.",
                    fix="Verify Bot Access Token is valid and has correct permissions.",
                ),
            )
        if self.health.last_error:
            issues.append(
                ChannelIssue(
                    kind=IssueKind.RUNTIME,
                    severity=IssueSeverity.ERROR,
                    message=self.health.last_error,
                ),
            )
        return issues
