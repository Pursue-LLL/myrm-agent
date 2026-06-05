"""Slack Bot channel — Events API + Web API + Socket Mode.

Inbound: Events API webhook / Socket Mode WebSocket → _emit_inbound
  - Messages: _parse_message_event (DM/channel/thread)
  - Interactions: _handle_block_actions (Button clicks, Select choices)
  - Bot self-message filtering via bot_user_id + subtype check
Outbound:
  - Streaming: chat.startStream / chat.appendStream / chat.stopStream (native AI UX)
  - Status: assistant.threads.setStatus (AI Agent "is thinking..." indicator)
  - Fallback: chat.postMessage / chat.update (when streaming unavailable)
  - Files: getUploadURLExternal → PUT → completeUploadExternal (3-step upload)
  - Other: chat.delete / reactions.add

[INPUT]
- channels.core.base::BaseChannel (POS: Channel abstract base class)
- channels.providers.slack.api::SlackClient (POS: HTTP/API layer)
- channels.types::OutboundMessage, (POS: Provides ArtifactInfo, infer_language, infer_artifact_type.)

[OUTPUT]
- SlackChannel: Slack Bot bidirectional messaging Channel (Events API + Socket Mode)

[POS]
Slack Bot channel implementation with AI Agent status indicator support. Supports
DM/channel/thread messages, file upload, message edit/delete/reactions, Socket Mode
persistent connection, native AI streaming output, assistant thread status.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time

from myrm_agent_harness.infra.tracing import get_meter

from app.channels.core.base import BaseChannel
from app.channels.core.credentials import (
    credential_field,
    credential_spec,
)
from app.channels.providers.slack.api import SlackClient
from app.channels.providers.slack.thread_tracker import (
    ThreadTrackerMetrics,
)
from app.channels.reliability.reconnect import reconnect_loop
from app.channels.rendering.renderer import render
from app.channels.types import (
    ChannelCapabilities,
    ChannelIssue,
    ChannelStatus,
    InboundMessage,
    IssueKind,
    IssueSeverity,
    MediaAttachment,
    MediaType,
    OutboundMessage,
    RenderStyle,
    ReplyContext,
    ToolSummaryDisplay,
)

from .helpers import (
    build_blocks,
    parse_block_action,
    parse_media_attachments,
    strip_mention,
    verify_slack_signature,
)

logger = logging.getLogger(__name__)

_MAX_TEXT_LENGTH = 4000


class SlackChannel(BaseChannel):
    """Slack Bot channel using Events API + Web API."""

    name = "slack"
    credential_spec = credential_spec(
        "slackCredentials",
        bot_token=credential_field("botToken", "SLACK_BOT_TOKEN"),
        signing_secret=credential_field("signingSecret", "SLACK_SIGNING_SECRET"),
        app_token=credential_field("appToken", "SLACK_APP_TOKEN"),
    )
    capabilities = ChannelCapabilities(
        text=True,
        markdown=True,
        media=True,
        voice_message=False,
        file_upload=True,
        buttons=True,
        quick_replies=True,
        select_menus=True,
        interactive_callback=True,
        threads=True,
        edit=True,
        delete=True,
        reactions=True,
        typing_indicator=False,
        max_text_length=_MAX_TEXT_LENGTH,
    )
    render_style = RenderStyle(
        format="mrkdwn",
        max_text_length=_MAX_TEXT_LENGTH,
        tool_summary_display=ToolSummaryDisplay.COMPACT,
    )

    def __init__(
        self,
        bot_token: str,
        *,
        signing_secret: str = "",
        app_token: str = "",
        require_thread_mention: bool = False,
        user_resolver_cache_ttl: int = 3600,
        user_resolver_cache_size: int = 1000,
        user_resolver_max_concurrent: int = 4,
        mention_annotation_limit: int = 20,
    ) -> None:
        super().__init__()
        self._signing_secret = signing_secret
        self._api = SlackClient(bot_token, app_token=app_token)
        self._bot_user_id: str = ""
        self._team_id: str = ""
        self._socket_task: asyncio.Task[None] | None = None
        self._stream_sent: dict[str, str] = {}
        self._active_thread_status: dict[str, str] = {}
        self._thread_parent_cache: dict[str, tuple[ReplyContext | None, float]] = {}
        self._cache_ttl = 300.0  # 5 minutes
        self._cache_max_size = 100
        self._require_thread_mention = require_thread_mention
        self._user_resolver_max_concurrent = user_resolver_max_concurrent
        self._mention_annotation_limit = mention_annotation_limit

        from app.channels.providers.slack.thread_tracker import (
            ThreadTracker,
        )
        from app.channels.providers.slack.user_resolver import (
            SlackUserResolver,
        )

        self._thread_tracker = ThreadTracker()
        self._user_resolver = SlackUserResolver(
            self._api,
            cache_ttl=user_resolver_cache_ttl,
            cache_max_size=user_resolver_cache_size,
        )

        # Metrics for cache monitoring
        meter = get_meter(__name__)
        self._cache_hit_counter = meter.create_counter(
            "slack_thread_cache_hits",
            description="Number of cache hits for thread parent messages",
        )
        self._cache_miss_counter = meter.create_counter(
            "slack_thread_cache_misses",
            description="Number of cache misses for thread parent messages",
        )
        self._cache_eviction_counter = meter.create_counter(
            "slack_thread_cache_evictions",
            description="Number of cache evictions (LRU)",
        )

    # ── Lifecycle ──────────────────────────────────────────────

    async def start(self) -> None:
        if not self._api._token:
            logger.info("Slack bot token not configured; channel idle")
            return
        try:
            info = await self._api.auth_test()
            self._bot_user_id = info["user_id"]
            self._team_id = info["team_id"]
        except Exception as exc:
            logger.warning("SlackChannel: startup failed: %s", exc)
            self._status = ChannelStatus.ERROR
            return
        self._status = ChannelStatus.RUNNING
        self._set_connected(True)

        if self._api._app_token:
            self._socket_task = asyncio.create_task(
                reconnect_loop(
                    self._socket_mode_once,
                    lambda: self._status,
                    channel_name="SlackChannel",
                )
            )

        logger.info("SlackChannel: started (bot_user_id=%s)", self._bot_user_id)

    async def stop(self) -> None:
        self._set_connected(False)
        self._status = ChannelStatus.STOPPED
        if self._socket_task:
            self._socket_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._socket_task
        await self._api.close()
        logger.info("SlackChannel: stopped")

    async def health_check(self) -> bool:
        if self._status not in (ChannelStatus.RUNNING, ChannelStatus.DEGRADED):
            return False
        return await self._api.health_check()

    def collect_issues(self) -> list[ChannelIssue]:
        issues: list[ChannelIssue] = []
        if not self._api._token or not self._api._app_token:
            missing = []
            if not self._api._token:
                missing.append("Bot Token (xoxb-)")
            if not self._api._app_token:
                missing.append("App-Level Token (xapp-)")
            issues.append(
                ChannelIssue(
                    kind=IssueKind.CONFIG,
                    severity=IssueSeverity.ERROR,
                    message=f"{', '.join(missing)} not configured.",
                    fix="Set SLACK_BOT_TOKEN and SLACK_APP_TOKEN, or configure in Settings → Channels → Slack.",
                )
            )
            return issues
        if self.health.last_error:
            issues.append(
                ChannelIssue(
                    kind=IssueKind.RUNTIME,
                    severity=IssueSeverity.ERROR,
                    message=self.health.last_error,
                )
            )
        return issues

    @property
    def thread_tracker_metrics(self) -> ThreadTrackerMetrics:
        """Export thread tracker metrics for monitoring.

        Business layer can use this to export metrics to Prometheus, DataDog,
        or logging systems. Framework provides the data structure; business
        layer decides how to use it.

        Example:
            metrics = slack_channel.thread_tracker_metrics
            prometheus_gauge.set(metrics.current_size)
            logger.info("Thread tracker: hit_rate=%.2f%%", metrics.get_hit_rate() * 100)
        """
        return self._thread_tracker.metrics

    # ── Outbound ───────────────────────────────────────────────

    async def send(self, msg: OutboundMessage) -> str | None:
        channel_id = msg.recipient_id
        thread_ts = msg.thread_id or (msg.metadata.get("thread_ts") if msg.metadata else None)
        last_ts: str | None = None

        if msg.content:
            chunks = render(msg, self.render_style)
            blocks = build_blocks(msg)
            for i, chunk in enumerate(chunks):
                payload: dict[str, object] = {
                    "channel": channel_id,
                    "text": chunk,
                }
                if thread_ts:
                    payload["thread_ts"] = thread_ts
                elif msg.reply_to_id:
                    payload["thread_ts"] = msg.reply_to_id
                if blocks and i == len(chunks) - 1:
                    payload["blocks"] = blocks

                ts = await self._api.post_message(payload)
                if ts:
                    last_ts = ts

                # Track thread participation
                actual_thread_ts = payload.get("thread_ts")
                if actual_thread_ts and isinstance(actual_thread_ts, str):
                    self._thread_tracker.add(actual_thread_ts)

        for attachment in msg.media:
            await self._api.upload_file(channel_id, attachment, thread_ts)

        await self._clear_assistant_status(channel_id)
        return last_ts

    async def send_placeholder(
        self,
        chat_id: str,
        text: str,
        *,
        thread_id: str | None = None,
    ) -> str | None:
        if thread_id:
            self._active_thread_status[chat_id] = thread_id
            await self._api.set_thread_status(chat_id, thread_id, "is thinking...")

            ts = await self._api.start_stream(chat_id, thread_id, text, self._team_id)
            if ts:
                self._stream_sent[ts] = text
                return ts

        payload: dict[str, object] = {"channel": chat_id, "text": text}
        if thread_id:
            payload["thread_ts"] = thread_id
            self._thread_tracker.add(thread_id)
        return await self._api.post_message(payload)

    async def edit_message(self, chat_id: str, message_id: str, text: str) -> None:
        if message_id in self._stream_sent:
            prev = self._stream_sent[message_id]
            if text.startswith(prev):
                delta = text[len(prev) :]
                if delta:
                    ok = await self._api.append_stream(chat_id, message_id, delta)
                    if ok:
                        self._stream_sent[message_id] = text
                        return
            self._stream_sent.pop(message_id, None)

        await self._api.update_message(chat_id, message_id, text)

    async def edit_placeholder_message(
        self,
        chat_id: str,
        message_id: str,
        msg: OutboundMessage,
    ) -> None:
        if message_id in self._stream_sent:
            self._stream_sent.pop(message_id, None)
            blocks = build_blocks(msg)
            payload: dict[str, object] = {
                "channel": chat_id,
                "ts": message_id,
            }
            chunks = render(msg, self.render_style)
            if chunks:
                payload["markdown_text"] = chunks[0]
            if blocks:
                payload["blocks"] = blocks
            ok = await self._api.stop_stream(chat_id, message_id, payload)
            if ok:
                await self._clear_assistant_status(chat_id)
                return

        await self.edit_message(chat_id, message_id, msg.content)
        await self._clear_assistant_status(chat_id)

    async def delete_message(self, chat_id: str, message_id: str) -> None:
        await self._api.delete_message(chat_id, message_id)
        await self._clear_assistant_status(chat_id)

    async def react_to_message(self, chat_id: str, message_id: str, emoji: str) -> None:
        if not emoji:
            return
        await self._api.add_reaction(chat_id, message_id, emoji.strip(":"))

    async def _clear_assistant_status(self, chat_id: str) -> None:
        """Clear assistant thread status if one was set for this chat."""
        thread_ts = self._active_thread_status.pop(chat_id, None)
        if thread_ts:
            await self._api.set_thread_status(chat_id, thread_ts, "")

    # ── Inbound ────────────────────────────────────────────────

    def verify_request(self, body: bytes, timestamp: str, signature: str) -> bool:
        """Verify Slack request signature."""
        return verify_slack_signature(self._signing_secret, body, timestamp, signature)

    async def handle_event(self, event_data: dict[str, object]) -> dict[str, str] | None:
        """Process a Slack Events API callback or interactive payload."""
        if event_data.get("type") == "url_verification":
            return {"challenge": str(event_data.get("challenge", ""))}

        if event_data.get("type") == "block_actions":
            await self._handle_block_actions(event_data)
            return None

        event = event_data.get("event", {})
        if not isinstance(event, dict):
            return None

        event_type = event.get("type")
        if event_type == "message" and not event.get("subtype"):
            msg = await self._parse_message_event(event)
            if msg:
                await self._emit_inbound(msg)
        elif event_type == "reaction_added":
            msg = self._parse_reaction_event(event)
            if msg:
                await self._emit_inbound(msg)

        return None

    _SLACK_EMOJI_MAP: dict[str, str] = {
        "+1": "👍",
        "thumbsup": "👍",
        "-1": "👎",
        "thumbsdown": "👎",
        "white_check_mark": "✅",
        "heavy_check_mark": "✅",
        "x": "❌",
        "no_entry": "🚫",
        "no_entry_sign": "🚫",
        "heart": "❤️",
        "handshake": "🤝",
        "muscle": "💪",
        "infinity": "♾",
        "star": "⭐",
    }

    def _parse_reaction_event(self, event: dict[str, object]) -> InboundMessage | None:
        """Convert a Slack reaction_added event to InboundMessage."""
        user = str(event.get("user", ""))
        if not user or user == self._bot_user_id:
            return None

        reaction_name = str(event.get("reaction", ""))
        emoji = self._SLACK_EMOJI_MAP.get(reaction_name, "")
        if not emoji:
            return None

        item = event.get("item", {})
        if not isinstance(item, dict):
            return None
        channel_id = str(item.get("channel", ""))
        target_ts = str(item.get("ts", ""))

        return self._build_inbound(
            sender_id=user,
            content=emoji,
            chat_id=channel_id,
            is_group=True,
            mentioned=True,
            message_id=target_ts,
            metadata={"reaction": True, "target_message_id": target_ts},
        )

    async def _handle_block_actions(self, payload: dict[str, object]) -> None:
        parsed = parse_block_action(payload, self._bot_user_id)
        if parsed is None:
            return

        sent_at = __import__("time").time()
        message_ts = parsed.get("message_ts")
        if message_ts:
            with contextlib.suppress(ValueError, TypeError):
                sent_at = float(message_ts)

        inbound = self._build_inbound(
            sender_id=str(parsed["user_id"]),
            content=str(parsed["content"]),
            sent_at=sent_at,
            sent_timezone="UTC",
            chat_id=str(parsed["channel_id"]),
            sender_name=(str(parsed["sender_name"]) if parsed.get("sender_name") else None),
            is_group=True,
            mentioned=True,
            metadata=(dict(parsed["metadata"]) if isinstance(parsed["metadata"], dict) else {}),
            message_id=str(parsed["message_ts"]),
        )
        await self._emit_inbound(inbound)

    def _evict_lru_cache(self) -> None:
        """Evict oldest entry from cache if exceeds max size."""
        if len(self._thread_parent_cache) >= self._cache_max_size:
            oldest_key = min(
                self._thread_parent_cache.keys(),
                key=lambda k: self._thread_parent_cache[k][1],
            )
            self._thread_parent_cache.pop(oldest_key, None)
            self._cache_eviction_counter.add(1)

    def _get_cached_parent(self, channel_id: str, thread_ts: str) -> ReplyContext | None | object:
        """Get cached thread parent with TTL refresh on access.

        Returns:
            ReplyContext: Cache hit with valid parent
            None: Cache hit but parent was None (not found)
            object(): Cache miss (sentinel value)
        """
        cache_key = f"{channel_id}:{thread_ts}"
        cached = self._thread_parent_cache.get(cache_key)
        if cached:
            parent, cache_time = cached
            if time.time() - cache_time < self._cache_ttl:
                # Refresh TTL on cache hit for active threads
                self._thread_parent_cache[cache_key] = (parent, time.time())
                self._cache_hit_counter.add(1)
                return parent
        # Cache miss (expired or not found)
        self._cache_miss_counter.add(1)
        return object()  # Sentinel for cache miss

    async def _fetch_thread_parent(self, channel_id: str, thread_ts: str) -> ReplyContext | None:
        """Fetch Slack thread parent message and parse into structured ReplyContext.

        Uses conversations.history API to retrieve the parent message by timestamp.
        Supports: text content, file attachments (image/document/video/audio).
        Returns: ReplyContext with message content, media attachments, sender info, timestamp.
        """
        try:
            resp = await self._api._http.post(
                "https://slack.com/api/conversations.history",
                json={
                    "channel": channel_id,
                    "latest": thread_ts,
                    "inclusive": True,
                    "limit": 1,
                },
                timeout=10.0,
            )
            data = resp.json()
            if not data.get("ok"):
                logger.debug("Failed to fetch thread parent (API error): %s", data.get("error"))
                return None

            messages = data.get("messages", [])
            if not messages or not isinstance(messages, list):
                return None

            parent_msg = messages[0]
            if not isinstance(parent_msg, dict):
                return None

            text = str(parent_msg.get("text", ""))
            content = text  # Keep original text for mention detection in auto-reply logic

            media_list: list[MediaAttachment] = []
            files = parent_msg.get("files", [])
            if isinstance(files, list):
                for f in files:
                    if not isinstance(f, dict):
                        continue
                    mimetype = str(f.get("mimetype", ""))
                    url = str(f.get("url_private", ""))
                    filename = str(f.get("name", ""))

                    if mimetype.startswith("image/"):
                        media_list.append(MediaAttachment(media_type=MediaType.IMAGE, url=url or None))
                    elif mimetype.startswith("video/"):
                        media_list.append(MediaAttachment(media_type=MediaType.VIDEO, url=url or None))
                    elif mimetype.startswith("audio/"):
                        media_list.append(MediaAttachment(media_type=MediaType.AUDIO, url=url or None))
                    else:
                        media_list.append(
                            MediaAttachment(
                                media_type=MediaType.DOCUMENT,
                                url=url or None,
                                filename=filename or None,
                                mime_type=mimetype or None,
                            )
                        )

            sender_id = str(parent_msg.get("user", "")) or None

            timestamp = None
            ts_str = parent_msg.get("ts")
            if ts_str:
                with contextlib.suppress(ValueError, TypeError):
                    timestamp = float(ts_str)

            # Resolve sender name via users.info API
            sender_name = None
            if sender_id:
                sender_name = await self._user_resolver.resolve_user(sender_id)

            return ReplyContext(
                message_id=thread_ts,
                content=content,
                media=tuple(media_list),
                sender_id=sender_id,
                sender_name=sender_name,
                timestamp=timestamp,
            )
        except Exception:
            logger.debug("Failed to fetch thread parent %s in %s", thread_ts, channel_id)
            return None

    async def _annotate_mentions(self, text: str) -> str:
        """Annotate Slack mention tokens with human-readable names.

        Transforms <@U12345> → <@U12345> (Alice) for better Agent context.
        Limits to 20 mentions per message, resolves with max 4 concurrent API calls.
        Preserves original token for Agent to reply with mentions if needed.

        Args:
            text: Message text potentially containing <@USER_ID> tokens

        Returns:
            Annotated text with names, or original text if no mentions or resolution fails

        Example:
            Input:  "<@U123> and <@U456> please review"
            Output: "<@U123> (Alice) and <@U456> (Bob) please review"
        """
        if not text:
            return text

        # 1. Extract unique mention IDs
        import re

        mention_pattern = re.compile(r"<@([A-Z0-9]+)>")
        matches = mention_pattern.findall(text)
        if not matches:
            return text

        # Deduplicate while preserving order
        seen: set[str] = set()
        mention_ids: list[str] = []
        for mid in matches:
            if mid not in seen:
                seen.add(mid)
                mention_ids.append(mid)

        # 2. Limit mentions per message (prevent abuse)
        if len(mention_ids) > self._mention_annotation_limit:
            logger.debug(
                "Slack mention annotation: limiting %d mentions to %d",
                len(mention_ids),
                self._mention_annotation_limit,
            )
            mention_ids = mention_ids[: self._mention_annotation_limit]

        # 3. Batch resolve with concurrency limit
        names = await self._user_resolver.resolve_batch(mention_ids, max_concurrent=self._user_resolver_max_concurrent)

        # 4. Replace mentions in text
        def replace_fn(match: re.Match[str]) -> str:
            user_id = match.group(1)
            name = names.get(user_id)
            if name:
                return f"<@{user_id}> ({name})"
            return match.group(0)  # Keep original if resolution failed

        return mention_pattern.sub(replace_fn, text)

    async def _parse_message_event(self, event: dict[str, object]) -> InboundMessage | None:
        user_id = str(event.get("user", ""))
        if user_id == self._bot_user_id or not user_id:
            return None

        text = str(event.get("text", ""))
        channel_id = str(event.get("channel", ""))
        channel_type = str(event.get("channel_type", ""))
        is_group = channel_type in ("channel", "group")
        ts = str(event.get("ts", ""))
        thread_ts = event.get("thread_ts")

        mentioned = f"<@{self._bot_user_id}>" in text if self._bot_user_id else False
        media_list = parse_media_attachments(event)

        if not text.strip() and not media_list:
            return None

        metadata: dict[str, object] = {
            "ts": ts,
            "thread_ts": str(thread_ts) if thread_ts else None,
            "channel_type": channel_type,
        }

        # Annotate mentions before stripping bot mention
        text = await self._annotate_mentions(text)

        content = strip_mention(text, self._bot_user_id)

        reply_to = None
        if thread_ts:
            # Auto-reply if bot has participated in this thread
            if not self._require_thread_mention and self._thread_tracker.contains(str(thread_ts)):
                mentioned = True

            # Check cache first
            cached_parent = self._get_cached_parent(channel_id, str(thread_ts))

            if isinstance(cached_parent, ReplyContext) or cached_parent is None:
                # Cache hit
                reply_to = cached_parent
            else:
                # Cache miss, fetch from API
                reply_to = await self._fetch_thread_parent(channel_id, str(thread_ts))

                # Update cache
                cache_key = f"{channel_id}:{thread_ts}"
                self._evict_lru_cache()
                self._thread_parent_cache[cache_key] = (reply_to, time.time())

            # Thread auto-reply: Check if thread should auto-respond without @mention
            if not mentioned and not self._require_thread_mention and reply_to:
                parent_has_mention = (
                    reply_to.content and f"<@{self._bot_user_id}>" in reply_to.content if reply_to.content else False
                )

                # Auto-reply if bot-initiated or parent has @mention
                if reply_to.sender_id == self._bot_user_id or parent_has_mention:
                    mentioned = True

        sent_at = __import__("time").time()
        if ts:
            with contextlib.suppress(ValueError, TypeError):
                sent_at = float(ts)

        return self._build_inbound(
            sender_id=user_id,
            content=content,
            sent_at=sent_at,
            sent_timezone="UTC",
            chat_id=channel_id,
            is_group=is_group,
            mentioned=mentioned,
            media=tuple(media_list),
            reply_to_id=str(thread_ts) if thread_ts else None,
            reply_to=reply_to,
            thread_id=str(thread_ts) if thread_ts else None,
            metadata=metadata,
            message_id=ts,
        )

    # ── Socket Mode ────────────────────────────────────────────

    async def _socket_mode_once(self) -> None:
        """Single Socket Mode session. reconnect_loop handles retry on failure."""
        ws_url = await self._api.open_socket_connection()

        import websockets

        async with websockets.connect(ws_url) as ws:
            import json as json_mod

            async for raw in ws:
                payload = json_mod.loads(raw)
                envelope_id = payload.get("envelope_id")
                if envelope_id:
                    await ws.send(json_mod.dumps({"envelope_id": envelope_id}))

                payload_type = payload.get("type", "")
                inner = payload.get("payload", {})
                if not isinstance(inner, dict):
                    continue

                if payload_type == "events_api" and inner.get("event"):
                    event = inner["event"]
                    if not isinstance(event, dict):
                        continue
                    evt_type = event.get("type")
                    if evt_type == "message" and not event.get("subtype"):
                        msg = await self._parse_message_event(event)
                        if msg:
                            await self._emit_inbound(msg)
                    elif evt_type == "reaction_added":
                        msg = self._parse_reaction_event(event)
                        if msg:
                            await self._emit_inbound(msg)
                elif payload_type == "interactive" and inner.get("type") == "block_actions":
                    await self._handle_block_actions(inner)

    async def fetch_history(self, chat_id: str, limit: int = 15) -> list[InboundMessage]:
        """Fetch recent historical messages from Slack channel."""
        try:
            resp = await self._api._http.post(
                "https://slack.com/api/conversations.history",
                json={
                    "channel": chat_id,
                    "limit": limit,
                },
                timeout=10.0,
            )
            data = resp.json()
            if not data.get("ok"):
                logger.warning(
                    "Slack: Failed to fetch history for %s (API error): %s",
                    chat_id,
                    data.get("error"),
                )
                return []

            messages = data.get("messages", [])
            if not messages or not isinstance(messages, list):
                return []

            inbounds = []
            for msg_dict in messages:
                if not isinstance(msg_dict, dict):
                    continue

                msg_dict["channel"] = chat_id
                user = str(msg_dict.get("user", ""))
                if user == self._bot_user_id or msg_dict.get("bot_id"):
                    continue

                inbound = await self._parse_message_event(msg_dict)
                if inbound:
                    inbounds.append(inbound)

            return list(reversed(inbounds))
        except Exception as e:
            logger.warning("Failed to fetch Slack history for %s: %s", chat_id, e)
            return []
