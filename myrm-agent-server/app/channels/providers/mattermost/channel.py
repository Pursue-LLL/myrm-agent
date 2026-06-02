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
- app.channels.core.mixins::CachedGroupMixin (POS: Reusable channel capability mixin components.)

[OUTPUT]
- MattermostChannel: Mattermost bidirectional channel (WebSocket inbound + REST API v4 outbound).

[POS]
app.channels.providers.mattermost.channel — Mattermost WebSocket inbound + REST API v4 outbound.
"""

from __future__ import annotations

import asyncio
import json
import logging

import httpx

from app.channels import BaseChannel, InboundMessage, OutboundMessage
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
    MediaType,
    RenderStyle,
    ToolSummaryDisplay,
)

from .api import MattermostClient

logger = logging.getLogger(__name__)

_MAX_MSG_LENGTH = 16383


class MattermostChannel(BaseChannel, CachedGroupMixin):
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

    # Mattermost reactions arrive as platform shortcodes (``+1``, ``thumbsup``,
    # ``white_check_mark`` …). Translate each into the canonical Unicode
    # symbol that ``parse_approval_command`` recognises, so the routing layer
    # can stay agnostic of channel-specific naming.
    _REACTION_EMOJI_MAP: dict[str, str] = {
        "+1": "\U0001F44D",
        "thumbsup": "\U0001F44D",
        "white_check_mark": "\u2705",
        "heavy_check_mark": "\u2705",
        "heart": "\u2764",
        "muscle": "\U0001F4AA",
        "handshake": "\U0001F91D",
        "infinity": "\u267E",
        "star": "\u2B50",
        "-1": "\U0001F44E",
        "thumbsdown": "\U0001F44E",
        "x": "\u274C",
        "no_entry": "\U0001F6AB",
        "no_entry_sign": "\U0001F6AB",
    }

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

    # ── WebSocket Inbound ──────────────────────────────────────────

    async def _ws_connect(self) -> None:
        """Single WebSocket session — runs until connection drops."""
        async for event in self._api.stream_events():
            event_type = event.get("event", "")
            if event_type == "posted":
                await self._handle_posted(event)
            elif event_type == "reaction_added":
                await self._handle_reaction_added(event)

    async def _handle_reaction_added(self, event: dict[str, object]) -> None:
        """Convert a Mattermost ``reaction_added`` WebSocket event to InboundMessage.

        Mattermost emoji names map onto the unified Unicode model
        (``parse_approval_command``) via :pyattr:`_REACTION_EMOJI_MAP`. Reactions
        whose ``user_id`` matches the bot are filtered upstream by the inbound
        pipeline (``BaseChannel._emit_inbound``), but we also short-circuit here
        for clarity.
        """
        data = event.get("data")
        if not isinstance(data, dict):
            return

        reaction_raw = data.get("reaction", "")
        if not isinstance(reaction_raw, str):
            return
        try:
            reaction = json.loads(reaction_raw)
        except (json.JSONDecodeError, TypeError):
            return
        if not isinstance(reaction, dict):
            return

        user_id = str(reaction.get("user_id", ""))
        if not user_id or user_id == self._bot_id:
            return

        emoji_name = str(reaction.get("emoji_name", "")).strip()
        emoji = self._REACTION_EMOJI_MAP.get(emoji_name)
        if not emoji:
            return

        channel_id = str(reaction.get("channel_id", ""))
        target_post_id = str(reaction.get("post_id", ""))
        if not channel_id or not target_post_id:
            return

        channel_type = str(data.get("channel_type", ""))
        is_group = channel_type not in ("D", "")

        inbound = InboundMessage(
            channel="mattermost",
            sender_id=user_id,
            content=emoji,
            chat_id=channel_id,
            is_group=is_group,
            mentioned=True,
            message_id=target_post_id,
            metadata={
                "platform": "mattermost",
                "channel_type": channel_type,
                "reaction": True,
                "target_message_id": target_post_id,
            },
        )
        await self._emit_inbound(inbound)

    async def _handle_posted(self, event: dict[str, object]) -> None:
        """Parse a 'posted' WebSocket event into InboundMessage."""
        data = event.get("data")
        if not isinstance(data, dict):
            return

        post_raw = data.get("post", "")
        if not isinstance(post_raw, str):
            return

        try:
            post = json.loads(post_raw)
        except (json.JSONDecodeError, TypeError):
            return

        if not isinstance(post, dict):
            return

        user_id = str(post.get("user_id", ""))
        if not user_id or user_id == self._bot_id:
            return

        message = str(post.get("message", "")).strip()
        if not message:
            return

        channel_id = str(post.get("channel_id", ""))
        post_id = str(post.get("id", ""))
        root_id = str(post.get("root_id", ""))

        channel_type = str(data.get("channel_type", ""))
        is_group = channel_type not in ("D", "")

        mentioned = self._check_mentioned(data, is_group)
        message = self._strip_bot_mention(message)

        sender_name = str(data.get("sender_name", ""))

        file_ids = post.get("file_ids")
        media = self._build_inbound_media(file_ids)

        sent_at = __import__("time").time()
        create_at = post.get("create_at")
        if create_at is not None:
            try:
                sent_at = float(create_at) / 1000.0
            except (ValueError, TypeError):
                pass

        inbound = InboundMessage(
            channel="mattermost",
            sender_id=user_id,
            content=message,
            sent_at=sent_at,
            sent_timezone="UTC",
            chat_id=channel_id,
            sender_name=sender_name or None,
            is_group=is_group,
            mentioned=mentioned,
            media=tuple(media),
            thread_id=root_id or None,
            metadata={
                "platform": "mattermost",
                "channel_type": channel_type,
            },
            message_id=post_id or None,
        )
        await self._emit_inbound(inbound)

    def _check_mentioned(self, data: dict[str, object], is_group: bool) -> bool:
        """Check if the bot was @mentioned. DMs always count as mentioned."""
        if not is_group:
            return True
        mentions_raw = data.get("mentions", "")
        if not isinstance(mentions_raw, str) or not mentions_raw:
            return False
        try:
            mention_ids = json.loads(mentions_raw)
            if isinstance(mention_ids, list):
                return self._bot_id in mention_ids
        except (json.JSONDecodeError, TypeError):
            pass
        return False

    def _strip_bot_mention(self, text: str) -> str:
        """Remove @botname mention from message text."""
        if not self._bot_name:
            return text
        stripped = text.replace(f"@{self._bot_name}", "").strip()
        return stripped or text

    def _build_inbound_media(
        self,
        file_ids: object,
    ) -> list[MediaAttachment]:
        """Build MediaAttachment list from post file_ids."""
        if not isinstance(file_ids, list) or not file_ids:
            return []
        attachments: list[MediaAttachment] = []
        for fid in file_ids:
            if not isinstance(fid, str) or not fid:
                continue
            url = f"{self._api.api_url}/files/{fid}"
            attachments.append(
                MediaAttachment(
                    media_type=MediaType.DOCUMENT,
                    url=url,
                    filename=fid,
                ),
            )
        return attachments

    # ── Outbound ──────────────────────────────────────────────────

    async def send(self, msg: OutboundMessage) -> str | None:
        channel_id = msg.recipient_id
        if not channel_id or not msg.content:
            return None

        root_id = msg.reply_to_id or ""
        if not root_id and msg.metadata and isinstance(msg.metadata, dict):
            root_id = str(msg.metadata.get("thread_id", "")) or ""

        last_id: str | None = None
        try:
            file_ids = await self._upload_media(channel_id, msg.media)

            for chunk in render(msg, self.render_style):
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

        return last_id

    async def _upload_media(
        self,
        channel_id: str,
        media: tuple[MediaAttachment, ...],
    ) -> list[str]:
        """Upload media attachments and return file_ids."""
        if not media:
            return []

        file_ids: list[str] = []
        http = self._api._get_http()
        for attachment in media:
            if not attachment.url:
                continue
            try:
                from app.channels.media import (
                    MediaDownloadConfig,
                    MediaDownloader,
                )

                config = MediaDownloadConfig(timeout_seconds=30.0)
                downloader = MediaDownloader(http_client=http, enable_default_cache=True)
                result = await downloader.download(attachment.url, config=config)
                if not result.success or not result.data:
                    continue
                filename = attachment.filename or "file"
                fid = await self._api.upload_file(channel_id, filename, result.data)
                if fid:
                    file_ids.append(fid)
            except Exception as exc:
                logger.debug("Mattermost: media upload failed for %s: %s", attachment.filename, exc)
        return file_ids

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
