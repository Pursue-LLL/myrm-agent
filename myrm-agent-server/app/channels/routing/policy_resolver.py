"""Policy resolution for inbound messages.

Resolves the sender's system user_id by checking DM/group policies,
pairing status, and WhatsApp LID fallback logic.

[INPUT]
- channels.core.bus::MessageBus (POS: async message bus)
- channels.protocols.pairing::PairingStore, ChannelPolicyProvider (POS: identity binding and policy protocols)
- channels.routing.context_buffer::GroupContextBuffer (POS: group chat context accumulation buffer)
- channels.routing.message_effects::MessageEffects (POS: typing/reaction/placeholder side effects)

[OUTPUT]
- PolicyResolver: InboundMessage → user_id resolution (or None to skip)

[POS]
Policy resolution module extracted from Router core routing logic.
Handles DM/group policy evaluation, user identity resolution, and pairing state management.
Router holds an instance via composition and calls resolve_group_user / resolve_dm_user.
"""

from __future__ import annotations

import dataclasses
import logging
import time
from collections.abc import Callable

from app.channels.protocols.pairing import (
    ChannelPolicyProvider,
    DmPolicy,
    GroupPolicy,
    GroupTriggerMode,
    PairingStatus,
    PairingStore,
)
from app.channels.routing.context_buffer import GroupContextBuffer
from app.channels.routing.message_effects import MessageEffects
from app.channels.routing.policy_resolver_support import BoundedCooldownMap, GroupFollowUpTracker
from app.channels.types import (
    METADATA_EXPLICIT_MENTION_KEY,
    METADATA_GUEST_TURN_KEY,
    ContextEntry,
    InboundMessage,
)

logger = logging.getLogger(__name__)

ChannelLookup = Callable[[str], object | None]


class PolicyResolver:
    """Resolves sender identity via DM/group policy and pairing store.

    Stateless with respect to messages — all mutable state (context buffer)
    is injected from the Router.
    """

    def __init__(
        self,
        pairing: PairingStore,
        policy: ChannelPolicyProvider | None,
        context_buffer: GroupContextBuffer,
        fx: MessageEffects,
        get_channel: ChannelLookup,
    ) -> None:
        self._pairing = pairing
        self._policy = policy
        self._context_buffer = context_buffer
        self._fx = fx
        self._get_channel = get_channel
        self._cooldown = BoundedCooldownMap()
        # Thread-Aware active multiround follower-up tracker
        self._tracker = GroupFollowUpTracker(ttl_seconds=600.0, max_size=1000)

    async def resolve_group_user(
        self,
        msg: InboundMessage,
    ) -> tuple[str, InboundMessage] | None:
        """Resolve user_id for group messages via GroupPolicy + trigger check.

        Returns (user_id, possibly-modified msg) or None to skip.
        Flow: groupPolicy → enabled_groups → trigger check → context buffer → default_user_id.
        """
        if msg.user_id and msg.metadata.get("trusted_inbound") == "control_plane":
            return msg.user_id, msg

        policy = await self._get_group_policy(msg.channel)

        if policy == GroupPolicy.DISABLED:
            logger.warning("PolicyResolver: group disabled for %s, ignoring", msg.channel)
            return None

        enabled = await self._get_enabled_groups()
        is_guest_turn = False
        if msg.chat_id not in enabled:
            if await self._is_guest_mention_allowed(msg):
                is_guest_turn = True
            else:
                return None

        chat_id = msg.chat_id or msg.sender_id

        should_respond, cleaned = await self._should_respond_in_group(msg)
        if not should_respond:
            self._context_buffer.append(
                chat_id,
                ContextEntry(sender_id=msg.sender_id, content=msg.content, timestamp=time.monotonic()),
            )
            return None

        # Clean thread-mute message from processing to prevent agent triggering on confirmations
        if cleaned == "___MUTE_CONFIRMED___":
            return None

        if cleaned != msg.content:
            msg = dataclasses.replace(msg, content=cleaned)

        context = self._context_buffer.drain(chat_id)
        if context:
            msg = dataclasses.replace(msg, context_messages=context)

        if self._policy:
            default_uid = await self._policy.get_default_user_id()
            if default_uid:
                if is_guest_turn:
                    guest_meta = dict(msg.metadata or {})
                    guest_meta[METADATA_GUEST_TURN_KEY] = "1"
                    msg = dataclasses.replace(msg, metadata=guest_meta)
                elif msg.thread_id:
                    self._tracker.activate(f"{msg.channel}:{msg.chat_id}:{msg.thread_id}")
                return default_uid, msg

        return None

    async def resolve_dm_user(self, msg: InboundMessage) -> str | None:
        """Resolve the sender's system user_id via DM policy + PairingStore."""
        if msg.user_id:
            return msg.user_id

        policy = await self._get_dm_policy(msg.channel)

        if policy == DmPolicy.DISABLED:
            logger.warning("PolicyResolver: DM disabled for %s, ignoring", msg.channel)
            return None

        user_id: str | None = None
        if policy == DmPolicy.OPEN:
            user_id = await self._pairing.resolve(msg.channel, msg.sender_id)
            if not user_id and msg.sender_id.endswith("@lid"):
                user_id = await self._resolve_lid_fallback(msg, allow_default_fallback=True)
            if not user_id and self._policy:
                user_id = await self._policy.get_default_user_id()
        elif policy == DmPolicy.PAIRING:
            user_id = await self._resolve_with_pairing(msg)
        else:
            user_id = await self._resolve_allowlist(msg)

        if user_id and msg.sender_name:
            await self._touch_display_name(msg)

        return user_id

    async def _touch_display_name(self, msg: InboundMessage) -> None:
        """Best-effort update of display_name when the sender's name changes."""
        try:
            await self._pairing.touch_display_name(msg.channel, msg.sender_id, msg.sender_name or "")
        except Exception:
            logger.debug("touch_display_name failed for %s/%s", msg.channel, msg.sender_id, exc_info=True)

    async def _should_respond_in_group(self, msg: InboundMessage) -> tuple[bool, str]:
        """Determine whether the bot should respond based on trigger config.

        Returns (should_respond, cleaned_content).
        Supports thread-aware exempt-mention dynamics and explicit mute commands.
        """
        # 1. Group Whitelist Check (freeResponseChats)
        if self._policy and hasattr(self._policy, "get_free_response_chats"):
            whitelist = await self._policy.get_free_response_chats(msg.channel)
            if whitelist and msg.chat_id in whitelist:
                return True, msg.content

        # 2. Check for explicit mute command
        cleaned_content = msg.content.strip()
        if cleaned_content in ("/mute", "/shutup", "闭嘴", "别吵"):
            thread_key = f"{msg.channel}:{msg.chat_id}:{msg.thread_id}" if msg.thread_id else None
            if thread_key and self._tracker.is_active(thread_key):
                self._tracker.mute(thread_key)
                # Send microsecond-level mute confirmation, bypassing LLM agents
                await self._fx.send_mute_reply(msg)
                return True, "___MUTE_CONFIRMED___"

        # 3. Explicit Mention Trigger
        if msg.mentioned:
            return True, msg.content

        # 4. Thread-Aware Exemption Check (exempt-mention for active multiround thread follow-up)
        if msg.thread_id:
            thread_key = f"{msg.channel}:{msg.chat_id}:{msg.thread_id}"
            if self._tracker.is_active(thread_key):
                return True, msg.content

        # 5. Standard Static Trigger Mode Fallback
        mode, prefixes = await self._get_group_trigger(msg.channel)

        if mode == GroupTriggerMode.ALL:
            return True, msg.content

        if mode == GroupTriggerMode.PREFIX and prefixes:
            for prefix in prefixes:
                if prefix and msg.content.startswith(prefix):
                    return True, msg.content[len(prefix) :].strip()

        return False, msg.content

    async def _get_dm_policy(self, channel: str) -> DmPolicy:
        if self._policy:
            return await self._policy.get_dm_policy(channel)
        return DmPolicy.ALLOWLIST

    async def _get_group_policy(self, channel: str) -> GroupPolicy:
        if self._policy:
            return await self._policy.get_group_policy(channel)
        return GroupPolicy.DISABLED

    async def _get_group_trigger(self, channel: str) -> tuple[GroupTriggerMode, list[str]]:
        if self._policy:
            return await self._policy.get_group_trigger(channel)
        return GroupTriggerMode.MENTION_ONLY, []

    async def _get_enabled_groups(self) -> set[str]:
        if self._policy:
            return await self._policy.get_enabled_groups()
        return set()

    async def _is_guest_mention_allowed(self, msg: InboundMessage) -> bool:
        """Guest mode: one-shot explicit entity mention in a non-enabled group."""
        if not self._policy:
            return False
        guest_mode = await self._policy.get_guest_mode(msg.channel)
        if not guest_mode:
            return False
        meta = msg.metadata or {}
        return meta.get(METADATA_EXPLICIT_MENTION_KEY) == "1"

    async def _resolve_allowlist(self, msg: InboundMessage) -> str | None:
        """Allowlist mode: only ACTIVE pairings are processed, others silently ignored."""
        user_id = await self._pairing.resolve(msg.channel, msg.sender_id)
        if user_id:
            return user_id

        if msg.sender_id.endswith("@lid"):
            user_id = await self._resolve_lid_fallback(msg, allow_default_fallback=False)
            if user_id:
                return user_id

        status = await self._pairing.get_status(msg.channel, msg.sender_id)
        if status == PairingStatus.BLOCKED:
            logger.warning("PolicyResolver: blocked %s/%s", msg.channel, msg.sender_id)
            return None

        logger.warning("PolicyResolver: unpaired %s/%s (allowlist mode)", msg.channel, msg.sender_id)
        return None

    async def _resolve_lid_fallback(
        self,
        msg: InboundMessage,
        *,
        allow_default_fallback: bool = False,
    ) -> str | None:
        """Resolve a WhatsApp LID sender via verified LID→PN mapping."""
        ch = self._get_channel(msg.channel)
        lid_cache: dict[str, str] = getattr(ch, "_lid_to_pn", {})
        if lid_cache:
            pn = lid_cache.get(msg.sender_id)
            if pn:
                user_id = await self._pairing.resolve(msg.channel, pn)
                if user_id:
                    await self._pairing.bind(
                        msg.channel,
                        msg.sender_id,
                        user_id,
                        display_name=msg.sender_name,
                    )
                    logger.warning(
                        "PolicyResolver: LID auto-bound via verified mapping %s → %s (user=%s)",
                        msg.sender_id,
                        pn,
                        user_id,
                    )
                    return user_id

        if not allow_default_fallback or not self._policy:
            return None
        default_uid = await self._policy.get_default_user_id()
        if not default_uid:
            return None

        await self._pairing.bind(msg.channel, msg.sender_id, default_uid, display_name=msg.sender_name)
        logger.warning(
            "PolicyResolver: LID auto-bound to default user %s → %s (open policy)",
            msg.sender_id,
            default_uid,
        )
        return default_uid

    async def _resolve_with_pairing(self, msg: InboundMessage) -> str | None:
        """Pairing mode: auto-create PENDING for unknown senders."""
        user_id = await self._pairing.resolve(msg.channel, msg.sender_id)
        if user_id:
            return user_id

        if msg.sender_id.endswith("@lid"):
            user_id = await self._resolve_lid_fallback(msg, allow_default_fallback=False)
            if user_id:
                return user_id

        status = await self._pairing.get_status(msg.channel, msg.sender_id)
        if status == PairingStatus.BLOCKED:
            logger.warning("PolicyResolver: blocked %s/%s", msg.channel, msg.sender_id)
            return None

        if status == PairingStatus.PENDING:
            await self._rate_limited_pending_reply(msg)
            return None

        default_uid = ""
        if self._policy:
            default_uid = await self._policy.get_default_user_id() or ""
        await self._pairing.bind(
            msg.channel,
            msg.sender_id,
            default_uid,
            status=PairingStatus.PENDING,
            display_name=msg.sender_name,
        )
        logger.warning("PolicyResolver: auto-paired %s/%s as PENDING", msg.channel, msg.sender_id)
        await self._fx.send_pairing_request_reply(msg)
        self._cooldown.should_suppress(f"{msg.channel}:{msg.sender_id}")
        return None

    async def _rate_limited_pending_reply(self, msg: InboundMessage) -> None:
        """Send pending reply at most once per _PENDING_REPLY_COOLDOWN per sender."""
        key = f"{msg.channel}:{msg.sender_id}"
        if self._cooldown.should_suppress(key):
            return
        await self._fx.send_pending_reply(msg)
