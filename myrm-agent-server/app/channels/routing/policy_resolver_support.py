"""Support types for inbound policy resolution (cooldown + group follow-up tracking).

[INPUT]
- (stdlib only)

[OUTPUT]
- BoundedCooldownMap: TTL-bounded rate-limit map
- GroupFollowUpTracker: active group thread tracker for mention-exempt follow-up
- query_dm_policy, query_group_policy, query_group_trigger, query_enabled_groups, check_guest_mention_allowed: Policy provider query delegates

[POS]
Extracted helpers for PolicyResolver to keep the resolver module under line budget.
"""

from __future__ import annotations

import dataclasses
import logging
import time
from typing import TYPE_CHECKING, Callable

from app.channels.types import METADATA_GUEST_TURN_KEY

if TYPE_CHECKING:
    from app.channels.protocols.pairing import (
        ChannelPolicyProvider,
        DmPolicy,
        GroupPolicy,
        GroupTriggerMode,
        PairingStore,
    )
    from app.channels.routing.message_effects import MessageEffects
    from app.channels.types import InboundMessage

logger = logging.getLogger(__name__)

PENDING_REPLY_COOLDOWN = 300.0
PENDING_REPLY_MAX_SIZE = 10000


class BoundedCooldownMap:
    """Bounded map with TTL for rate-limiting, preventing unbounded memory growth under spam."""

    __slots__ = ("_ttl", "_max_size", "_entries")

    def __init__(
        self,
        ttl: float = PENDING_REPLY_COOLDOWN,
        max_size: int = PENDING_REPLY_MAX_SIZE,
    ) -> None:
        self._ttl = ttl
        self._max_size = max_size
        self._entries: dict[str, float] = {}

    def should_suppress(self, key: str) -> bool:
        """Return True if the key is still within cooldown (suppress the action)."""
        now = time.monotonic()
        last = self._entries.get(key)
        if last is not None and now - last < self._ttl:
            return True
        if len(self._entries) >= self._max_size:
            oldest_key = min(self._entries, key=lambda k: self._entries[k])
            self._entries.pop(oldest_key, None)
        self._entries[key] = now
        return False


class GroupFollowUpTracker:
    """Tracks active group threads/conversations for smart exempt-mention follow-up.

    Uses a bounded LRU eviction dict + strictly enforced TTL (10 minutes)
    to prevent memory growth while ensuring microsecond-level query speed.
    """

    def __init__(self, ttl_seconds: float = 600.0, max_size: int = 1000) -> None:
        self._ttl = ttl_seconds
        self._max_size = max_size
        self._active_threads: dict[str, float] = {}

    def activate(self, key: str) -> None:
        """Mark a thread/conversation as active with LRU eviction."""
        now = time.monotonic()
        if len(self._active_threads) >= self._max_size:
            oldest_key = min(self._active_threads, key=lambda k: self._active_threads[k])
            self._active_threads.pop(oldest_key, None)
        self._active_threads[key] = now

    def is_active(self, key: str) -> bool:
        """Check if active and refresh activity timestamp to keep the session alive."""
        now = time.monotonic()
        last_active = self._active_threads.get(key)
        if last_active is None:
            return False

        if now - last_active > self._ttl:
            self._active_threads.pop(key, None)
            return False

        self._active_threads[key] = now
        return True

    def mute(self, key: str) -> None:
        """Manually mute/deactivate a thread (e.g. via /mute or /shutup command)."""
        self._active_threads.pop(key, None)


async def query_dm_policy(
    policy_provider: ChannelPolicyProvider | None, channel: str
) -> DmPolicy:
    """Resolve DM policy with fallback to ALLOWLIST."""
    from app.channels.protocols.pairing import DmPolicy

    if policy_provider:
        return await policy_provider.get_dm_policy(channel)
    return DmPolicy.ALLOWLIST


async def query_group_policy(
    policy_provider: ChannelPolicyProvider | None, channel: str
) -> GroupPolicy:
    """Resolve group policy with fallback to DISABLED."""
    from app.channels.protocols.pairing import GroupPolicy

    if policy_provider:
        return await policy_provider.get_group_policy(channel)
    return GroupPolicy.DISABLED


async def query_group_trigger(
    policy_provider: ChannelPolicyProvider | None, channel: str
) -> tuple[GroupTriggerMode, list[str]]:
    """Resolve group trigger mode and prefix list with fallback."""
    from app.channels.protocols.pairing import GroupTriggerMode

    if policy_provider:
        return await policy_provider.get_group_trigger(channel)
    return GroupTriggerMode.MENTION_ONLY, []


async def query_enabled_groups(
    policy_provider: ChannelPolicyProvider | None,
) -> set[str]:
    """Retrieve enabled groups set with fallback to empty set."""
    if policy_provider:
        return await policy_provider.get_enabled_groups()
    return set()


async def check_guest_mention_allowed(
    policy_provider: ChannelPolicyProvider | None, msg: InboundMessage
) -> bool:
    """Guest mode: one-shot explicit entity mention in a non-enabled group."""
    from app.channels.types import METADATA_EXPLICIT_MENTION_KEY

    if not policy_provider:
        return False
    guest_mode = await policy_provider.get_guest_mode(msg.channel)
    if not guest_mode:
        return False
    meta = msg.metadata or {}
    return meta.get(METADATA_EXPLICIT_MENTION_KEY) == "1"


async def resolve_lid_fallback_helper(
    pairing: PairingStore,
    policy_provider: ChannelPolicyProvider | None,
    channel_lookup: Callable[[str], object | None],
    msg: InboundMessage,
    *,
    allow_default_fallback: bool = False,
) -> str | None:
    """Resolve a WhatsApp LID sender via verified LID→PN mapping."""
    ch = channel_lookup(msg.channel)
    lid_cache: dict[str, str] = getattr(ch, "_lid_to_pn", {})
    if lid_cache:
        pn = lid_cache.get(msg.sender_id)
        if pn:
            user_id = await pairing.resolve(msg.channel, pn)
            if user_id:
                await pairing.bind(
                    msg.channel,
                    msg.sender_id,
                    user_id,
                    display_name=msg.sender_name,
                )
                logger.warning(
                    "PolicyResolver: LID auto-bound via mapping %s → %s",
                    msg.sender_id,
                    pn,
                )
                return user_id

    if not allow_default_fallback or not policy_provider:
        return None
    default_uid = await policy_provider.get_default_user_id()
    if not default_uid:
        return None

    await pairing.bind(
        msg.channel, msg.sender_id, default_uid, display_name=msg.sender_name
    )
    logger.warning(
        "PolicyResolver: LID auto-bound to default user %s → %s",
        msg.sender_id,
        default_uid,
    )
    return default_uid


async def check_sender_daily_quota(
    pairing: PairingStore,
    msg: InboundMessage,
) -> tuple[bool, int, int]:
    """Check if paired_member sender has exceeded their configured daily quota.

    Returns (is_exceeded, daily_quota, usage_count).
    """
    if not hasattr(pairing, "get_pairing_detail"):
        return False, 0, 0
    pairing_detail = await pairing.get_pairing_detail(msg.channel, msg.sender_id)
    if not pairing_detail or pairing_detail[2] is None or pairing_detail[2] <= 0:
        return False, 0, 0

    daily_quota = pairing_detail[2]
    from app.database.connection import get_session
    from app.database.repositories.channel_message_repo import (
        ChannelMessageRepository,
    )

    async with get_session() as session:
        usage_count = await ChannelMessageRepository.get_daily_trigger_count(
            session, msg.channel, msg.sender_id
        )

    if usage_count >= daily_quota:
        return True, daily_quota, usage_count
    return False, daily_quota, usage_count


def is_exempt_diagnostic_command(content: str) -> bool:
    """Check if the inbound message is a read-only diagnostic command (/status, /quota, /help)."""
    tokens = content.strip().lower().split()
    if not tokens:
        return False
    if tokens[0] in ("/status", "/quota", "/help"):
        return True
    if len(tokens) > 1 and tokens[0].startswith("@") and tokens[1] in ("/status", "/quota", "/help"):
        return True
    return False


async def resolve_group_sender_identity(
    pairing: PairingStore,
    fx: MessageEffects,
    msg: InboundMessage,
    default_uid: str,
    tracker: GroupFollowUpTracker,
) -> tuple[str, InboundMessage] | None:
    """Arbitrate sender identity in an enabled group to enforce PoLP and prevent Confused Deputy privilege escalation."""
    sender_uid = await pairing.resolve(msg.channel, msg.sender_id)
    if sender_uid and sender_uid.startswith("paired_member_"):
        if not is_exempt_diagnostic_command(msg.content):
            is_exceeded, daily_quota, usage_count = await check_sender_daily_quota(pairing, msg)
            if is_exceeded:
                logger.warning(
                    "PolicyResolver: group sender %s/%s exceeded daily quota %d (used %d)",
                    msg.channel,
                    msg.sender_id,
                    daily_quota,
                    usage_count,
                )
                await fx.send_quota_exceeded_reply(msg, daily_quota)
                return None
        if msg.thread_id:
            tracker.activate(f"{msg.channel}:{msg.chat_id}:{msg.thread_id}")
        return sender_uid, msg

    if sender_uid == default_uid:
        if msg.thread_id:
            tracker.activate(f"{msg.channel}:{msg.chat_id}:{msg.thread_id}")
        return default_uid, msg

    guest_meta = dict(msg.metadata or {})
    guest_meta[METADATA_GUEST_TURN_KEY] = "1"
    if msg.thread_id:
        tracker.activate(f"{msg.channel}:{msg.chat_id}:{msg.thread_id}")
    return f"guest_{msg.channel}_{msg.sender_id}", dataclasses.replace(msg, metadata=guest_meta)


async def should_respond_in_group_support(
    policy: ChannelPolicyProvider | None,
    tracker: GroupFollowUpTracker,
    fx: MessageEffects,
    msg: InboundMessage,
) -> tuple[bool, str]:
    """Determine whether the bot should respond in group based on trigger config."""
    # 1. Group Whitelist Check (freeResponseChats)
    if policy and hasattr(policy, "get_free_response_chats"):
        whitelist = await policy.get_free_response_chats(msg.channel)
        if whitelist and msg.chat_id in whitelist:
            return True, msg.content

    # 2. Check for explicit mute command
    cleaned_content = msg.content.strip()
    if cleaned_content in ("/mute", "/shutup", "闭嘴", "别吵"):
        thread_key = (
            f"{msg.channel}:{msg.chat_id}:{msg.thread_id}"
            if msg.thread_id
            else None
        )
        if thread_key and tracker.is_active(thread_key):
            tracker.mute(thread_key)
            from app.channels.routing.follow_up import mute_tracked_thread

            mute_tracked_thread(msg.channel, msg.chat_id or msg.sender_id, msg.thread_id)
            await fx.send_mute_reply(msg)
            return True, "___MUTE_CONFIRMED___"

    # 3. Explicit Mention Trigger
    if msg.mentioned:
        return True, msg.content

    # 4. Thread-Aware Exemption Check (exempt-mention for active multiround thread follow-up)
    if msg.thread_id:
        thread_key = f"{msg.channel}:{msg.chat_id}:{msg.thread_id}"
        if tracker.is_active(thread_key):
            return True, msg.content

    # 5. Standard Static Trigger Mode Fallback
    mode, prefixes = await query_group_trigger(policy, msg.channel)
    from app.channels.protocols.pairing import GroupTriggerMode

    if mode == GroupTriggerMode.ALL:
        return True, msg.content

    if mode == GroupTriggerMode.PREFIX and prefixes:
        for prefix in prefixes:
            if prefix and msg.content.startswith(prefix):
                return True, msg.content[len(prefix) :].strip()

    return False, msg.content
