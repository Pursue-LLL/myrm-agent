"""Side-effect-free sender admission: would the access policy let this sender through to an agent turn?

[INPUT]
- app.channels.protocols.pairing::ChannelPolicyProvider, DmPolicy, GroupPolicy, PairingStore (POS: identity binding and policy protocols)
- app.channels.routing.policy_resolver_support::check_guest_mention_allowed, is_admin_sender, lid_mapped_phone, query_dm_policy, query_enabled_groups, query_group_policy (POS: policy lookups and the owner rule)

[OUTPUT]
- check_sender_admitted: the admission verdict for one inbound message

[POS]
The admission gates of PolicyResolver.resolve_group_user / resolve_dm_user without their side effects (replies,
quota, pending-pairing creation, LID binding, ledger writes). AgentRouter relies on it for work that must follow the
access policy but runs before those resolvers, such as event-triggered cron jobs.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.channels.protocols.pairing import DmPolicy, GroupPolicy
from app.channels.routing.policy_resolver_support import (
    check_guest_mention_allowed,
    is_admin_sender,
    lid_mapped_phone,
    query_dm_policy,
    query_enabled_groups,
    query_group_policy,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from app.channels.protocols.pairing import ChannelPolicyProvider, PairingStore
    from app.channels.types import InboundMessage


async def check_sender_admitted(
    pairing: PairingStore,
    policy_provider: ChannelPolicyProvider | None,
    channel_lookup: Callable[[str], object | None],
    msg: InboundMessage,
) -> bool:
    """Whether the access policy lets ``msg``'s sender through to an agent turn.

    Mirrors the admission gates of ``resolve_group_user`` / ``resolve_dm_user`` and nothing else: a control-plane
    forward, the group policy with enabled groups (or a guest @mention), the DM policy with an ACTIVE pairing.
    The owner is always admitted. Group admission is per chat, so a message that does not address the bot is still
    admitted; the daily quota and BotLoopGuard only cap chat turns and are not applied.
    """
    if msg.user_id and msg.metadata.get("trusted_inbound") == "control_plane":
        return True
    if msg.is_group:
        admitted = await _group_admitted(policy_provider, msg)
    else:
        admitted = await _dm_admitted(pairing, policy_provider, channel_lookup, msg)
    return admitted or await is_admin_sender(pairing, msg)


async def _group_admitted(policy_provider: ChannelPolicyProvider | None, msg: InboundMessage) -> bool:
    if await query_group_policy(policy_provider, msg.channel) == GroupPolicy.DISABLED:
        return False
    if msg.chat_id in await query_enabled_groups(policy_provider):
        return True
    return await check_guest_mention_allowed(policy_provider, msg)


async def _dm_admitted(
    pairing: PairingStore,
    policy_provider: ChannelPolicyProvider | None,
    channel_lookup: Callable[[str], object | None],
    msg: InboundMessage,
) -> bool:
    if msg.user_id:
        return True
    policy = await query_dm_policy(policy_provider, msg.channel)
    if policy == DmPolicy.DISABLED:
        return False
    return policy == DmPolicy.OPEN or await _has_active_pairing(pairing, channel_lookup, msg)


async def _has_active_pairing(
    pairing: PairingStore,
    channel_lookup: Callable[[str], object | None],
    msg: InboundMessage,
) -> bool:
    """Whether the sender holds an ACTIVE pairing, also through its verified LID mapping, without binding the LID."""
    if await pairing.resolve(msg.channel, msg.sender_id):
        return True
    phone = lid_mapped_phone(channel_lookup, msg) if msg.sender_id.endswith("@lid") else None
    return bool(phone and await pairing.resolve(msg.channel, phone))
