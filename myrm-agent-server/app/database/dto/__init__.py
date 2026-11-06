"""Data transfer objects.

[INPUT]
- .literals / .message / .chat / .pagination / .agent (POS: DTO modules)

[OUTPUT]
- every DTO, Literal alias, TypeVar and normalize_workspace_policy, re-exported.

[POS]
Aggregate exit of the DTO package; `app.database.dto` keeps its import path for 120 modules.
"""

from __future__ import annotations

from .agent import (
    AgentBase,
    AgentCreate,
    AgentListItem,
    AgentMemoryPolicyConfig,
    AgentProfileSnapshotItem,
    AgentResponse,
    AgentSessionPolicyConfig,
    AgentUpdate,
    CommandBindingConfig,
    ModelSelection,
    SkillConfig,
    ToolGatewayConfigDTO,
)
from .chat import (
    ChatBase,
    ChatCreate,
    ChatDetail,
    ChatDetailData,
    ChatDTO,
    ChatListItem,
    GenerateTitleRequest,
    TurnOutlineItem,
    UpdateSummaryRequest,
    UpdateTitleRequest,
    _TitleModelConfig,
)
from .literals import (
    AgentTypeLiteral,
    MemoryDecayProfileLiteral,
    MemoryExtractionPresetLiteral,
    PersonalityStyleLiteral,
    PromptModeLiteral,
    SecurityPresetLiteral,
    SessionResetModeLiteral,
    WorkspacePolicyLiteral,
    normalize_workspace_policy,
)
from .message import (
    CursorPage,
    MessageBase,
    MessageCreate,
    MessageDTO,
    MessageResponse,
)
from .pagination import (
    PaginatedResponse,
    PaginationMeta,
    PaginationParams,
    T,
)

__all__ = [
    "PersonalityStyleLiteral",
    "MemoryDecayProfileLiteral",
    "MemoryExtractionPresetLiteral",
    "PromptModeLiteral",
    "SecurityPresetLiteral",
    "WorkspacePolicyLiteral",
    "normalize_workspace_policy",
    "AgentTypeLiteral",
    "T",
    "MessageBase",
    "MessageDTO",
    "ChatDTO",
    "MessageCreate",
    "MessageResponse",
    "ChatBase",
    "ChatCreate",
    "_TitleModelConfig",
    "GenerateTitleRequest",
    "ChatListItem",
    "ChatDetail",
    "UpdateSummaryRequest",
    "TurnOutlineItem",
    "ChatDetailData",
    "CursorPage",
    "UpdateTitleRequest",
    "PaginationParams",
    "PaginationMeta",
    "PaginatedResponse",
    "ModelSelection",
    "AgentMemoryPolicyConfig",
    "SessionResetModeLiteral",
    "AgentSessionPolicyConfig",
    "SkillConfig",
    "CommandBindingConfig",
    "ToolGatewayConfigDTO",
    "AgentBase",
    "AgentCreate",
    "AgentUpdate",
    "AgentResponse",
    "AgentProfileSnapshotItem",
    "AgentListItem",
]
