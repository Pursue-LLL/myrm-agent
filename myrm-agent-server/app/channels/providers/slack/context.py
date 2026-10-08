"""Slack inbound context: thread-parent cache and mention annotation.

[INPUT]
- channels.providers.slack.api::SlackClient (POS: HTTP/API layer used to fetch the thread parent)
- channels.providers.slack.user_resolver::SlackUserResolver (POS: user id to display name resolution)
- channels.types::ReplyContext, MediaAttachment (POS: channel message value types)

[OUTPUT]
- SlackContextMixin: `_get_cached_parent` / `_fetch_thread_parent` / `_evict_lru_cache` and `_annotate_mentions`, the context enrichment SlackInboundMixin applies to each message

[POS]
Context half of Slack inbound. The host owns the API client, the caches and the resolver; the mixin only reads and fills them.
"""

from __future__ import annotations

import contextlib
import logging
import re
import time
from typing import TYPE_CHECKING

from app.channels.providers.slack.api import SlackClient
from app.channels.types import (
    MediaAttachment,
    MediaType,
    ReplyContext,
)

if TYPE_CHECKING:
    from opentelemetry.metrics import Counter

    from .user_resolver import SlackUserResolver

logger = logging.getLogger(__name__)


class SlackContextMixin:
    """Thread-parent cache and mention annotation for ``SlackChannel``.

    Requires the host class to provide the attributes below.
    """

    _api: SlackClient
    _user_resolver_max_concurrent: int
    _mention_annotation_limit: int
    _thread_parent_cache: dict[str, tuple[ReplyContext | None, float]]
    _cache_ttl: float
    _cache_max_size: int
    _cache_hit_counter: Counter
    _cache_miss_counter: Counter
    _cache_eviction_counter: Counter
    _user_resolver: SlackUserResolver

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
