"""Team-shared identity resolution for channel turns — pure mapping layer.

Resolves which conversation compartment an inbound turn executes in:

- Unbound, revoked, or DM turns → owner-personal compartment (existing
  behavior, default agent fallback).
- Group turns on a bound identity → shared team compartment keyed by the
  binding's stable identity id. Renames change the display name only.

[INPUT]
- channels.types::TopicContext, InboundMessage
- myrm_agent_harness.agent.security.team_identity (POS: compartment DTO)

[OUTPUT]
- ResolvedTeamIdentity: harness spec + memory namespace + fallback flag.

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

from app.channels.types import IdentityScopeMode, InboundMessage, TopicContext


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
