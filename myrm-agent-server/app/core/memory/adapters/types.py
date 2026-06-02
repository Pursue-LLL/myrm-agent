"""
[INPUT]
myrm_agent_harness.toolkits.memory.config::AgentMemoryPolicy (POS: 记忆策略配置)

[OUTPUT]
ResolvedMemoryBinding: Server 到 Harness 的记忆运行时绑定合同

[POS]
记忆适配器类型定义。集中表达 agent/channel/conversation/task、Shared Context 和 memory_policy 运行时边界。
"""

from __future__ import annotations

from dataclasses import dataclass

from myrm_agent_harness.toolkits.memory.config import AgentMemoryPolicy


@dataclass(frozen=True, slots=True)
class ResolvedMemoryBinding:
    agent_id: str
    namespaces: list[str]
    shared_context_ids: list[str]
    memory_policy: AgentMemoryPolicy | None = None
    channel_id: str | None = None
    conversation_id: str | None = None
    task_id: str | None = None
