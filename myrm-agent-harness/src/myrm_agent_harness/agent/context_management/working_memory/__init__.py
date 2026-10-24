"""Working memory marks package.

[INPUT]
- context_management.working_memory.marks::WorkingMemoryMark (POS: Core memory abstraction layer for message metadata tags, aligned with AgentScope MemoryBase contract while maintaining zero-LLM overhead and Prompt Cache safety.)

[OUTPUT]
- WorkingMemoryMark / IMMUNE_MARKS 及 mark 读写与驱逐免疫原语

[POS]
驱逐免疫标记的包级统一出口。仅向上下文管理层暴露 Working Memory 标记 API。
"""

from myrm_agent_harness.agent.context_management.working_memory.marks import (
    IMMUNE_MARKS,
    WorkingMemoryMark,
    get_message_marks,
    has_message_marks,
    is_eviction_immune,
    with_message_marks,
)

__all__ = [
    "IMMUNE_MARKS",
    "WorkingMemoryMark",
    "get_message_marks",
    "has_message_marks",
    "is_eviction_immune",
    "with_message_marks",
]
