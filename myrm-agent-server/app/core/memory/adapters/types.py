"""
[INPUT]
myrm_agent_harness.toolkits.context.spec::AgentContextOverlay, IncognitoPolicy (POS: context bundle specification)
myrm_agent_harness.toolkits.memory.config::AgentMemoryPolicy (POS: 记忆策略配置)

[OUTPUT]
ResolvedContextBinding: Server 到 Harness 的上下文运行时绑定合同

[POS]
上下文适配器类型定义。集中表达 agent/channel/conversation/task、Shared Context、memory_policy
与 ContextBundle volume 边界。
"""

from __future__ import annotations

from dataclasses import dataclass

from myrm_agent_harness.toolkits.context.spec import (
    CONTEXT_BUNDLE_SCHEMA_VERSION,
    DEFAULT_BUNDLE_ID,
    DEFAULT_SCENES,
    VOLUME_LAYOUT_VERSION,
    AgentContextOverlay,
    IncognitoPolicy,
)
from myrm_agent_harness.toolkits.memory.config import AgentMemoryPolicy


@dataclass(frozen=True, slots=True)
class ResolvedContextBinding:
    agent_id: str
    namespaces: list[str]
    shared_context_ids: list[str]
    memory_policy: AgentMemoryPolicy | None = None
    channel_id: str | None = None
    conversation_id: str | None = None
    task_id: str | None = None
    bundle_id: str = DEFAULT_BUNDLE_ID
    schema_version: int = CONTEXT_BUNDLE_SCHEMA_VERSION
    volume_layout_version: int = VOLUME_LAYOUT_VERSION
    active_scenes: tuple[str, ...] = tuple(scene.value for scene in DEFAULT_SCENES)
    incognito: IncognitoPolicy | None = None
    agent_overlay: AgentContextOverlay | None = None
