"""
[INPUT]
myrm_agent_harness.toolkits.memory.config::{AgentMemoryPolicy, MemoryScopeLevel, MemoryWritePolicy} (POS: 记忆策略配置)

[OUTPUT]
memory_policy_from_dict: Agent memory_policy 反序列化
memory_policy_to_dict: Agent memory_policy 序列化
derive_binding_namespaces: Server 运行时 binding 到 Harness namespaces 的派生

[POS]
记忆策略适配层。统一 AgentProfile memory_policy 与 Shared Context namespaces 的解析规则。
"""

from __future__ import annotations

from collections.abc import Mapping

from myrm_agent_harness.toolkits.memory.config import AgentMemoryPolicy, MemoryScopeLevel, MemoryWritePolicy

_SCOPE_ORDER: tuple[MemoryScopeLevel, ...] = (
    MemoryScopeLevel.GLOBAL,
    MemoryScopeLevel.AGENT,
    MemoryScopeLevel.CHANNEL,
    MemoryScopeLevel.CONVERSATION,
    MemoryScopeLevel.TASK,
)


def memory_policy_from_dict(raw: Mapping[str, object] | None) -> AgentMemoryPolicy | None:
    if raw is None:
        return None

    read_scopes_raw = raw.get("read_scopes")
    read_scopes = None
    if isinstance(read_scopes_raw, (list, tuple)):
        read_scopes = tuple(
            scope if isinstance(scope, MemoryScopeLevel) else MemoryScopeLevel(scope)
            for scope in read_scopes_raw
            if isinstance(scope, (MemoryScopeLevel, str))
        )

    write_policy_raw = raw.get("write_policy")
    write_policy = (
        write_policy_raw
        if isinstance(write_policy_raw, MemoryWritePolicy)
        else MemoryWritePolicy(write_policy_raw)
        if isinstance(write_policy_raw, str)
        else MemoryWritePolicy.INHERIT
    )
    agent_id_raw = raw.get("agent_id")
    channel_id_raw = raw.get("channel_id")
    conversation_id_raw = raw.get("conversation_id")
    task_id_raw = raw.get("task_id")

    return AgentMemoryPolicy(
        agent_id=agent_id_raw if isinstance(agent_id_raw, str) else None,
        channel_id=channel_id_raw if isinstance(channel_id_raw, str) else None,
        conversation_id=conversation_id_raw if isinstance(conversation_id_raw, str) else None,
        task_id=task_id_raw if isinstance(task_id_raw, str) else None,
        read_scopes=read_scopes,
        write_policy=write_policy,
    )


def memory_policy_to_dict(policy: AgentMemoryPolicy | None) -> dict[str, object] | None:
    if policy is None:
        return None
    return {
        "agent_id": policy.agent_id,
        "channel_id": policy.channel_id,
        "conversation_id": policy.conversation_id,
        "task_id": policy.task_id,
        "read_scopes": [scope.value for scope in policy.read_scopes] if policy.read_scopes is not None else None,
        "write_policy": policy.write_policy.value,
    }


def resolve_scope_identifiers(
    *,
    agent_id: str | None,
    channel_id: str | None,
    conversation_id: str | None,
    task_id: str | None,
    memory_policy: AgentMemoryPolicy | None,
) -> tuple[str | None, str | None, str | None, str | None]:
    if memory_policy is None:
        return agent_id, channel_id, conversation_id, task_id
    return (
        memory_policy.agent_id if memory_policy.agent_id is not None else agent_id,
        memory_policy.channel_id if memory_policy.channel_id is not None else channel_id,
        memory_policy.conversation_id if memory_policy.conversation_id is not None else conversation_id,
        memory_policy.task_id if memory_policy.task_id is not None else task_id,
    )


def derive_binding_namespaces(
    *,
    namespaces: list[str] | None,
    shared_context_ids: list[str] | None,
    agent_id: str | None,
    channel_id: str | None,
    conversation_id: str | None,
    task_id: str | None,
    memory_policy: AgentMemoryPolicy | None,
) -> list[str]:
    resolved_agent_id, resolved_channel_id, resolved_conversation_id, resolved_task_id = resolve_scope_identifiers(
        agent_id=agent_id,
        channel_id=channel_id,
        conversation_id=conversation_id,
        task_id=task_id,
        memory_policy=memory_policy,
    )

    candidates: dict[MemoryScopeLevel, str] = {
        MemoryScopeLevel.GLOBAL: "global",
        MemoryScopeLevel.AGENT: f"agent:{resolved_agent_id or 'default'}",
    }
    if resolved_channel_id:
        candidates[MemoryScopeLevel.CHANNEL] = f"channel:{resolved_channel_id}"
    if resolved_conversation_id:
        candidates[MemoryScopeLevel.CONVERSATION] = f"conversation:{resolved_conversation_id}"
    if resolved_task_id:
        candidates[MemoryScopeLevel.TASK] = f"task:{resolved_task_id}"

    if memory_policy is not None:
        levels = memory_policy.read_scopes or _SCOPE_ORDER
        scoped = [candidates[level] for level in _SCOPE_ORDER if level in levels and level in candidates]
        return list(dict.fromkeys([*scoped, *_shared_context_namespaces(shared_context_ids)]))

    base_namespaces = list(namespaces or [candidates[MemoryScopeLevel.GLOBAL], candidates[MemoryScopeLevel.AGENT]])
    derived = [candidates[MemoryScopeLevel.GLOBAL], candidates[MemoryScopeLevel.AGENT]]
    if resolved_channel_id:
        derived.append(candidates[MemoryScopeLevel.CHANNEL])
    if resolved_conversation_id:
        derived.append(candidates[MemoryScopeLevel.CONVERSATION])
    if resolved_task_id:
        derived.append(candidates[MemoryScopeLevel.TASK])
    return list(dict.fromkeys([*base_namespaces, *derived, *_shared_context_namespaces(shared_context_ids)]))


def _shared_context_namespaces(shared_context_ids: list[str] | None) -> list[str]:
    if not shared_context_ids:
        return []
    namespaces: list[str] = []
    for context_id in shared_context_ids:
        normalized = context_id.strip()
        if normalized:
            namespaces.append(f"shared:{normalized}")
    return namespaces
