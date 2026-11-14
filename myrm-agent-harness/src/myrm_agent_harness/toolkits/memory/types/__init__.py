"""[INPUT]
- .base::BaseMemory (POS: 记忆基础模型)
- .enums (POS: 记忆枚举)
- .records (POS: 具体记忆模型)
- .search (POS: 检索结果模型)

[OUTPUT]
- 全部记忆枚举、基础模型、具体模型、检索结果与 `AnyMemory` 联合类型

[POS]
`myrm_agent_harness.toolkits.memory.types` 的唯一门面；实现按枚举/基类/记录/检索分层。
"""

from __future__ import annotations

from .base import (
    ARCHIVE_RETENTION_DAYS,
    BaseMemory,
    EvidenceReference,
    MemoryLifecycle,
    MemoryMutationRef,
    MemoryMutationResult,
    MemoryScope,
    ProfileAttributeSnapshot,
    archive_retention_stamps,
)
from .enums import (
    ClaimConflictState,
    ClaimGraphState,
    ConflictResolution,
    DigestKind,
    EvaporationState,
    MemoryStatus,
    MemoryTier,
    MemoryType,
    PendingResolutionAction,
    RuleSource,
    ToolRulePriority,
)
from .records import (
    ClaimMemory,
    ConversationMemory,
    EpisodicMemory,
    IntegrationMemory,
    PreferenceType,
    ProceduralMemory,
    ProfileEntry,
    SemanticMemory,
    TaskDigestMemory,
)
from .search import HitSource, MemorySearchResult, PendingRecord, PendingStatus, RecallDebugTrace

AnyMemory = (
    SemanticMemory | EpisodicMemory | ConversationMemory | ProceduralMemory | IntegrationMemory | TaskDigestMemory
)

# Forward references are resolved here so every subclass sees the complete model set.
BaseMemory.model_rebuild()
SemanticMemory.model_rebuild()
EpisodicMemory.model_rebuild()
ProceduralMemory.model_rebuild()
ClaimMemory.model_rebuild()
IntegrationMemory.model_rebuild()
TaskDigestMemory.model_rebuild()

__all__ = [
    "ARCHIVE_RETENTION_DAYS",
    "AnyMemory",
    "BaseMemory",
    "ClaimConflictState",
    "ClaimGraphState",
    "ClaimMemory",
    "ConflictResolution",
    "ConversationMemory",
    "DigestKind",
    "EpisodicMemory",
    "EvaporationState",
    "EvidenceReference",
    "HitSource",
    "IntegrationMemory",
    "MemoryLifecycle",
    "MemoryMutationRef",
    "MemoryMutationResult",
    "MemoryScope",
    "MemorySearchResult",
    "MemoryStatus",
    "MemoryTier",
    "MemoryType",
    "PendingRecord",
    "PendingResolutionAction",
    "PendingStatus",
    "PreferenceType",
    "ProceduralMemory",
    "ProfileAttributeSnapshot",
    "ProfileEntry",
    "RecallDebugTrace",
    "RuleSource",
    "SemanticMemory",
    "TaskDigestMemory",
    "ToolRulePriority",
    "archive_retention_stamps",
]
