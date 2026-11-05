"""Kanban API request/response schemas.

[INPUT]
pydantic::BaseModel/Field (POS: data model base)

[OUTPUT]
Every kanban request/response model, re-exported for the routers and the SDK.

[POS]
Aggregate exit of the kanban schema package: one module per API area, one import path for callers.
"""

from __future__ import annotations

from .boards import (
    AgentTaskCounts,
    BoardCreate,
    BoardListResponse,
    BoardResponse,
    BoardSummaryResponse,
    BoardUpdate,
)
from .decompose import (
    ApplyDecomposeRequest,
    DecomposeChildResponse,
    DecomposeOutcomeResponse,
)
from .diagnostics import (
    DiagnosticActionResponse,
    DiagnosticSummaryResponse,
    TaskDiagnosticResponse,
    TaskDiagnosticsResponse,
)
from .links import (
    CommentCreate,
    DependencyListResponse,
    DependencyRequest,
    DependencyResponse,
    EdgeListResponse,
)
from .pipeline import (
    PipelineEstimateRequest,
    PipelineEstimateResponse,
    PipelineInstantiateRequest,
    PipelineInstantiateResponse,
    PipelineQuestionGroupResponse,
    PipelineQuestionResponse,
    PipelineRoleResponse,
    PipelineTaskGraphVariantResponse,
    PipelineTaskSeedResponse,
    PipelineTemplateDetailResponse,
    PipelineTemplateListResponse,
    PipelineTemplateResponse,
)
from .planning import (
    PlanRevisionItemRequest,
    PlanRevisionRequest,
    PlanRevisionResponse,
)
from .race import (
    RaceDecideRequest,
    RaceDecideResponse,
    RaceEstimateResponse,
    RaceFileChange,
    RaceLaneChangesResponse,
    RaceLaneFileResponse,
    RaceLaneResponse,
    RaceLaneSpec,
    RaceLanesResponse,
    RaceStartRequest,
    RaceStartResponse,
)
from .spec import (
    ApplySpecRequest,
    SpecifyAllResponse,
    SpecifyOutcomeResponse,
)
from .task_responses import (
    AttachmentInfo,
    BoardEventListResponse,
    BoardEventResponse,
    EventListResponse,
    EventResponse,
    ReclaimResponse,
    RunListResponse,
    RunResponse,
    TaskListResponse,
    TaskResponse,
)
from .tasks import (
    ApproveTaskRequest,
    BulkActionItemResult,
    BulkActionRequest,
    BulkActionResponse,
    PromoteRequest,
    PromoteResponse,
    ReclaimRequest,
    RejectTaskRequest,
    TaskCreate,
    TaskMoveRequest,
    TaskUpdate,
    UnmetParent,
)

__all__ = [
    "BoardCreate",
    "BoardUpdate",
    "BoardResponse",
    "AgentTaskCounts",
    "BoardSummaryResponse",
    "BoardListResponse",
    "TaskCreate",
    "TaskUpdate",
    "TaskMoveRequest",
    "PromoteRequest",
    "UnmetParent",
    "PromoteResponse",
    "ReclaimRequest",
    "ApproveTaskRequest",
    "RejectTaskRequest",
    "BulkActionRequest",
    "BulkActionItemResult",
    "BulkActionResponse",
    "DiagnosticActionResponse",
    "TaskDiagnosticResponse",
    "DiagnosticSummaryResponse",
    "TaskDiagnosticsResponse",
    "AttachmentInfo",
    "TaskResponse",
    "TaskListResponse",
    "ReclaimResponse",
    "RunResponse",
    "EventResponse",
    "RunListResponse",
    "EventListResponse",
    "BoardEventResponse",
    "BoardEventListResponse",
    "CommentCreate",
    "DependencyRequest",
    "DependencyResponse",
    "DependencyListResponse",
    "EdgeListResponse",
    "ApplySpecRequest",
    "SpecifyOutcomeResponse",
    "SpecifyAllResponse",
    "DecomposeChildResponse",
    "DecomposeOutcomeResponse",
    "ApplyDecomposeRequest",
    "PipelineQuestionResponse",
    "PipelineQuestionGroupResponse",
    "PipelineRoleResponse",
    "PipelineTaskSeedResponse",
    "PipelineTaskGraphVariantResponse",
    "PipelineTemplateResponse",
    "PipelineTemplateDetailResponse",
    "PipelineTemplateListResponse",
    "PipelineInstantiateRequest",
    "PipelineInstantiateResponse",
    "PipelineEstimateRequest",
    "PipelineEstimateResponse",
    "PlanRevisionItemRequest",
    "PlanRevisionRequest",
    "PlanRevisionResponse",
    "RaceLaneSpec",
    "RaceStartRequest",
    "RaceEstimateResponse",
    "RaceStartResponse",
    "RaceLaneResponse",
    "RaceLanesResponse",
    "RaceDecideRequest",
    "RaceDecideResponse",
    "RaceFileChange",
    "RaceLaneChangesResponse",
    "RaceLaneFileResponse",
]
