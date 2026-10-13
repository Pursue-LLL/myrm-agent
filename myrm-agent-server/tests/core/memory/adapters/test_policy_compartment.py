"""Namespace derivation under a memory policy and conversation-compartment confinement."""

from __future__ import annotations

from myrm_agent_harness.toolkits.memory.config import (
    AgentMemoryPolicy,
    MemoryScopeLevel,
    MemoryWritePolicy,
)

from app.core.memory.adapters.policy import compartment_memory_policy, derive_binding_namespaces


def _derive(
    *,
    namespaces: list[str] | None,
    policy: AgentMemoryPolicy | None,
    conversation_id: str | None = "chat-1",
    shared_context_ids: list[str] | None = None,
    project_id: str | None = None,
) -> list[str]:
    return derive_binding_namespaces(
        namespaces=namespaces,
        shared_context_ids=shared_context_ids,
        agent_id="default",
        channel_id="telegram",
        conversation_id=conversation_id,
        task_id=None,
        project_id=project_id,
        memory_policy=policy,
    )


def test_policy_keeps_extra_namespaces_after_scoped_reads() -> None:
    policy = AgentMemoryPolicy(read_scopes=(MemoryScopeLevel.CONVERSATION,))

    assert _derive(namespaces=["ident:team"], policy=policy) == ["conversation:chat-1", "ident:team"]


def test_policy_orders_scoped_extra_then_shared_namespaces() -> None:
    policy = AgentMemoryPolicy(read_scopes=(MemoryScopeLevel.CONVERSATION,))

    derived = _derive(namespaces=["ident:team"], policy=policy, shared_context_ids=["kb"])

    assert derived == ["conversation:chat-1", "ident:team", "shared:kb"]


def test_policy_without_extras_is_unchanged() -> None:
    policy = AgentMemoryPolicy(read_scopes=(MemoryScopeLevel.GLOBAL, MemoryScopeLevel.AGENT))

    assert _derive(namespaces=None, policy=policy) == ["global", "agent:default"]


def test_policy_branch_deduplicates_extra_namespaces() -> None:
    policy = AgentMemoryPolicy(read_scopes=(MemoryScopeLevel.CONVERSATION,))

    assert _derive(namespaces=["conversation:chat-1", "ident:team"], policy=policy) == [
        "conversation:chat-1",
        "ident:team",
    ]


def test_project_branch_still_strips_foreign_project_extras() -> None:
    policy = AgentMemoryPolicy(read_scopes=(MemoryScopeLevel.CONVERSATION,))

    derived = _derive(namespaces=["project:other", "ident:team"], policy=policy, project_id="mine")

    assert derived == ["project:mine", "conversation:chat-1", "ident:team"]


def test_compartment_policy_confines_reads_writes_and_extraction() -> None:
    confined = compartment_memory_policy(None)

    assert confined.read_scopes == (MemoryScopeLevel.CONVERSATION,)
    assert confined.write_policy == MemoryWritePolicy.INHERIT
    assert confined.allow_l3_extraction is False


def test_compartment_policy_overrides_wider_profile_policy_but_keeps_identifiers() -> None:
    profile = AgentMemoryPolicy(
        agent_id="planner",
        task_id="task-9",
        read_scopes=(MemoryScopeLevel.GLOBAL, MemoryScopeLevel.AGENT),
        write_policy=MemoryWritePolicy.AGENT,
        allow_l3_extraction=True,
        auto_cleanup=True,
    )

    confined = compartment_memory_policy(profile)

    assert confined.read_scopes == (MemoryScopeLevel.CONVERSATION,)
    assert confined.write_policy == MemoryWritePolicy.INHERIT
    assert confined.allow_l3_extraction is False
    assert (confined.agent_id, confined.task_id, confined.auto_cleanup) == ("planner", "task-9", True)
    assert profile.read_scopes == (MemoryScopeLevel.GLOBAL, MemoryScopeLevel.AGENT)
