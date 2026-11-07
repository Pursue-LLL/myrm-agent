"""[INPUT]
- .enums (POS: 看板枚举与派生集合)
- .metadata (POS: metadata 约定)
- .models (POS: 看板数据模型)

[OUTPUT]
- 全部看板类型、枚举与 metadata 助手

[POS]
`myrm_agent_harness.toolkits.kanban.types` 的唯一门面；实现按枚举/metadata/模型分层。
"""

from myrm_agent_harness.toolkits.kanban.types.enums import (
    _ACTIVE_STATUSES,
    _PRIORITY_ORDER,
    _TERMINAL_STATUSES,
    _TRIAGE_ALLOWED_TARGETS,
    BlockKind,
    TaskEventKind,
    TaskExecutionOutcome,
    TaskPriority,
    TaskRunOutcome,
    TaskStatus,
)
from myrm_agent_harness.toolkits.kanban.types.metadata import (
    KANBAN_COMPLETION_INTENT_KEY,
    KANBAN_SOURCE_CHAT_METADATA_KEY,
    clear_completion_intent,
    extract_source_chat_id,
    has_completion_intent,
    inherit_source_chat_metadata,
)
from myrm_agent_harness.toolkits.kanban.types.models import (
    BoardSettings,
    KanbanBoard,
    KanbanTask,
    TaskAttachment,
    TaskClaim,
    TaskEdge,
    TaskEvent,
    TaskExecutionResult,
    TaskRun,
    TaskTimeoutError,
    VerificationResult,
)

__all__ = [
    "KANBAN_COMPLETION_INTENT_KEY",
    "KANBAN_SOURCE_CHAT_METADATA_KEY",
    "BlockKind",
    "BoardSettings",
    "KanbanBoard",
    "KanbanTask",
    "TaskAttachment",
    "TaskClaim",
    "TaskEdge",
    "TaskEvent",
    "TaskEventKind",
    "TaskExecutionOutcome",
    "TaskExecutionResult",
    "TaskPriority",
    "TaskRun",
    "TaskRunOutcome",
    "TaskStatus",
    "TaskTimeoutError",
    "VerificationResult",
    "_ACTIVE_STATUSES",
    "_PRIORITY_ORDER",
    "_TERMINAL_STATUSES",
    "_TRIAGE_ALLOWED_TARGETS",
    "clear_completion_intent",
    "extract_source_chat_id",
    "has_completion_intent",
    "inherit_source_chat_metadata",
]
