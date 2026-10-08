"""Slack inbound: Events API / interactive payload parsing, thread-parent cache and mention annotation.

[INPUT]
- channels.providers.slack.api::SlackClient (POS: HTTP/API layer)
- channels.providers.slack.helpers (POS: signature verification, block action and media parsing)
- channels.types::InboundMessage, ReplyContext, MediaAttachment (POS: channel message value types)

[OUTPUT]
- SlackInboundMixin: verify_request, handle_event and the message / reaction / block_actions parsers used by SlackChannel

[POS]
Inbound half of SlackChannel. The host owns credentials, the API client and the caches; the mixin only parses events.
"""

from __future__ import annotations

import contextlib
import logging
import time
from typing import TYPE_CHECKING

from app.channels.providers.slack.api import SlackClient
from app.channels.types import (
    InboundMessage,
    MediaAttachment,
    MediaType,
    ReplyContext,
)

from .helpers import (
    parse_block_action,
    parse_media_attachments,
    strip_mention,
    verify_slack_signature,
)

if TYPE_CHECKING:
    from opentelemetry.metrics import Counter

    from .thread_tracker import ThreadTracker
    from .user_resolver import SlackUserResolver

logger = logging.getLogger(__name__)


class SlackInboundMixin:
    """Slack inbound event parsing for ``SlackChannel``.

    Requires the host class to provide the attributes below plus ``_emit_inbound`` / ``_build_inbound``
    from ``BaseChannel``.
    """

    _api: SlackClient
    _signing_secret: str
    _bot_user_id: str
    _require_thread_mention: bool
    _user_resolver_max_concurrent: int
    _mention_annotation_limit: int
    _thread_parent_cache: dict[str, tuple[ReplyContext | None, float]]
    _cache_ttl: float
    _cache_max_size: int
    _cache_hit_counter: Counter
    _cache_miss_counter: Counter
    _cache_eviction_counter: Counter
    _thread_tracker: ThreadTracker
    _user_resolver: SlackUserResolver

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

        # Slack sets bot_id on bot-authored events; used to keep thread auto-reply
        # implicit mentions human-only (bot-to-bot loop prevention).
        sender_is_bot = bool(event.get("bot_id"))

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
            # Auto-reply if bot has participated in this thread (human senders only)
            if not sender_is_bot and not self._require_thread_mention and self._thread_tracker.contains(str(thread_ts)):
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

                # Auto-reply if bot-initiated or parent has @mention (human senders only:
                # a bot posting in our thread must not wake the agent)
                if not sender_is_bot and (reply_to.sender_id == self._bot_user_id or parent_has_mention):
                    mentioned = True

        sent_at = __import__("time").time()
        if ts:
            with contextlib.suppress(ValueError, TypeError):
                sent_at = float(ts)

        sender_name = None
        if user_id:
            try:
                sender_name = await self._user_resolver.resolve_user(user_id)
            except Exception:
                logger.debug("Failed to resolve Slack sender name for %s", user_id)

        return self._build_inbound(
            sender_id=user_id,
            content=content,
            sent_at=sent_at,
            sent_timezone="UTC",
            chat_id=channel_id,
            is_group=is_group,
            is_bot=sender_is_bot,
            mentioned=mentioned,
            media=tuple(media_list),
            reply_to_id=str(thread_ts) if thread_ts else None,
            reply_to=reply_to,
            thread_id=str(thread_ts) if thread_ts else None,
            sender_name=sender_name,
            metadata=metadata,
            message_id=ts,
        )
