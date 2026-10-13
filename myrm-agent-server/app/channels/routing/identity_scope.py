"""Team-shared identity resolution for channel turns — pure mapping layer.

Resolves which conversation compartment an inbound turn executes in:

- Owner DM turns → owner-personal compartment (default agent fallback).
- Group turns on a bound identity → shared team compartment keyed by the
  binding's stable identity id. Renames change the display name only.
- Group turns without a binding and DM turns from guests or paired members →
  a stable per-chat (or per-sender) compartment. Private memory never reaches
  them; they only read and write their own compartment.

[INPUT]
- channels.types::TopicContext, InboundMessage
- myrm_agent_harness.agent.security.team_identity (POS: compartment DTO)
- app.core.memory.adapters.policy::compartment_memory_policy (POS: memory policy confinement)

[OUTPUT]
- ResolvedTeamIdentity: harness spec + memory namespace + fallback flag.
- is_untrusted_sender(): guest / paired-member predicate shared by the fence and the data plane.
- TurnMemoryScope / resolve_turn_memory_scope(): memory policy, compartment namespaces
  and recall gating for one turn.

[POS]
Pure deterministic mapping. No DB, no LLM, no prompt text — safe to call on
every inbound turn with zero prompt-cache impact.
"""

from __future__ import annotations

from dataclasses import dataclass

from myrm_agent_harness.agent.security.team_identity import (
    CredentialTrack,
    TeamIdentityScope,
    TeamIdentitySpec,
    credential_track_for,
    memory_namespace_for,
    sanitize_identity_id,
)
from myrm_agent_harness.toolkits.memory.config import AgentMemoryPolicy

from app.channels.types import METADATA_GUEST_TURN_KEY, IdentityScopeMode, InboundMessage, TopicContext
from app.core.memory.adapters.policy import compartment_memory_policy

_UNTRUSTED_USER_ID_PREFIXES = ("guest_", "paired_member_")


@dataclass(frozen=True, slots=True)
class ResolvedTeamIdentity:
    """Resolved compartment for one inbound turn."""

    spec: TeamIdentitySpec
    memory_namespace: str | None
    is_fallback: bool


def _baseline_identity_id(channel: str) -> str:
    return sanitize_identity_id(f"{channel}-baseline")


def default_identity_id(channel: str, chat_id: str, thread_id: str | None) -> str:
    """Derive a stable identity id for a binding (rename-safe)."""
    suffix = thread_id or "channel"
    return sanitize_identity_id(f"{channel}-{chat_id}-{suffix}")


def resolve_team_identity(
    topic: TopicContext | None,
    msg: InboundMessage,
) -> ResolvedTeamIdentity:
    """Map a topic binding + inbound message to a team identity spec."""
    if topic is None or topic.identity_revoked or not topic.agent_id:
        return ResolvedTeamIdentity(
            spec=TeamIdentitySpec(),
            memory_namespace=None,
            is_fallback=True,
        )
    if not msg.is_group:
        return ResolvedTeamIdentity(
            spec=TeamIdentitySpec(
                scope=TeamIdentityScope.PERSONAL,
                identity_id="owner",
                credential_track=CredentialTrack.PERSONAL,
                memory_namespace=memory_namespace_for("owner"),
                is_fallback=False,
            ),
            memory_namespace=None,
            is_fallback=False,
        )
    if topic.identity_scope == IdentityScopeMode.INHERIT:
        identity_id = _baseline_identity_id(msg.channel)
    else:
        identity_id = sanitize_identity_id(topic.identity_id or f"{msg.channel}-{topic.topic_id}")
    track = credential_track_for(is_group=True, scope=TeamIdentityScope.SHARED)
    return ResolvedTeamIdentity(
        spec=TeamIdentitySpec(
            scope=TeamIdentityScope.SHARED,
            identity_id=identity_id,
            credential_track=track,
            memory_namespace=memory_namespace_for(identity_id),
            is_fallback=False,
        ),
        memory_namespace=memory_namespace_for(identity_id),
        is_fallback=False,
    )


def is_untrusted_sender(user_id: str, msg: InboundMessage) -> bool:
    """Whether the turn comes from a guest, an unpaired sender or a non-admin paired member."""
    return user_id.startswith(_UNTRUSTED_USER_ID_PREFIXES) or bool(msg.metadata and msg.metadata.get(METADATA_GUEST_TURN_KEY))


@dataclass(frozen=True, slots=True)
class TurnMemoryScope:
    """Memory binding inputs for one inbound turn.

    ``is_compartment`` marks turns confined to a compartment: their recall must not reach
    owner-private history either.
    """

    policy: AgentMemoryPolicy | None
    extra_namespaces: tuple[str, ...]
    is_compartment: bool


def resolve_turn_memory_scope(
    msg: InboundMessage,
    team_identity: ResolvedTeamIdentity,
    *,
    untrusted: bool,
    profile_policy: AgentMemoryPolicy | None,
) -> TurnMemoryScope:
    """Decide which memory the turn may read and write.

    Owner DMs keep the owner's memory untouched. Group turns (any sender) and guest or
    paired-member DMs are confined to a compartment that always exists: the bound team
    identity, otherwise a stable per-chat id. Group sessions are keyed by chat, so owner and
    guests share one conversation there and must share one compartment too.
    """
    if not (msg.is_group or untrusted):
        return TurnMemoryScope(policy=profile_policy, extra_namespaces=(), is_compartment=False)
    namespace = team_identity.memory_namespace or _chat_compartment_namespace(msg)
    return TurnMemoryScope(
        policy=compartment_memory_policy(profile_policy),
        extra_namespaces=(namespace,),
        is_compartment=True,
    )


def _chat_compartment_namespace(msg: InboundMessage) -> str:
    """Stable compartment of an unbound chat. The session key rotates with resets; this id does not."""
    if msg.is_group:
        return memory_namespace_for(default_identity_id(msg.channel, msg.chat_id or msg.sender_id, msg.thread_id))
    return memory_namespace_for(default_identity_id(f"{msg.channel}-dm", msg.sender_id, msg.thread_id))
