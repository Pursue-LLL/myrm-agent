"""Kanban API request/response schemas.

[POS] Pydantic models for kanban API endpoints.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class BoardCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str = ""
    max_concurrent_tasks: int = Field(3, ge=1, le=50)
    heartbeat_interval_seconds: int = Field(30, ge=10, le=600)
    zombie_timeout_seconds: int = Field(120, ge=30, le=1800)
    max_retries_per_task: int = Field(3, ge=0, le=20)
    auto_block_after_consecutive_failures: int = Field(5, ge=1, le=50)
    specify_max_tokens: int = Field(6000, ge=1500, le=32000)
    auto_specify_on_create: bool = False
    default_workdir: str | None = Field(
        None,
        max_length=1024,
        description="Default workspace directory for tasks on this board.",
    )


class BoardUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    max_concurrent_tasks: int | None = Field(None, ge=1, le=50)
    specify_max_tokens: int | None = Field(None, ge=1500, le=32000)
    auto_specify_on_create: bool | None = None
    default_workdir: str | None = Field(
        None,
        max_length=1024,
        description="Default workspace directory for tasks on this board.",
    )


class BoardResponse(BaseModel):
    board_id: str
    name: str
    description: str
    settings: dict[str, int | bool | str | None]
    created_at: datetime
    updated_at: datetime


class AgentTaskCounts(BaseModel):
    """Per-agent task distribution (non-archived only)."""

    agent_id: str | None = None
    counts: dict[str, int] = {}
    total: int = 0


class BoardSummaryResponse(BaseModel):
    board: BoardResponse
    task_counts: dict[str, int]
    total_tasks: int
    dispatcher_active: bool = False
    by_agent: list[AgentTaskCounts] = []
    oldest_ready_age_seconds: int | None = None


class BoardListResponse(BaseModel):
    items: list[BoardResponse]
    total: int


class TaskCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)
    description: str = ""
    priority: str = "normal"
    parent_task_id: str | None = None
    agent_id: str | None = None
    workspace_path: str | None = Field(
        None,
        max_length=1024,
        description="Working directory for this task. Overrides board default_workdir.",
    )
    branch: str | None = Field(
        None,
        max_length=255,
        description="Git branch name. When set, creates an isolated worktree for this task.",
    )
    max_retries: int = Field(3, ge=0, le=20)
    depends_on: list[str] = Field(default_factory=list)
    extra_skill_ids: list[str] = Field(
        default_factory=list,
        description="Task-specific skills appended to the agent profile's defaults.",
    )
    attachment_ids: list[str] = Field(
        default_factory=list,
        max_length=10,
        description="File IDs from /api/files/upload to attach to this task (max 10).",
    )
    completion_criteria: str | list[dict[str, str | int]] | None = Field(
        None,
        description=(
            "Acceptance criteria for completion verification. "
            "Plain string for semantic-only check, or structured list: "
            '[{"type": "shell", "command": "test -f /output.csv"}, '
            '{"type": "semantic", "criteria": "report includes all data"}]'
        ),
    )
    max_runtime_seconds: int | None = Field(
        None,
        ge=10,
        le=86400,
        description="Per-task timeout in seconds (10s–24h). Falls back to system default when unset.",
    )
    initial_status: str | None = Field(
        None,
        description="Initial status: triage / backlog / ready / blocked. Defaults to backlog if depends_on, else ready.",
    )


class TaskUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    priority: str | None = None
    agent_id: str | None = None
    extra_skill_ids: list[str] | None = Field(
        None,
        description="Replace task-level skills. Pass [] to clear.",
    )
    attachment_ids: list[str] | None = Field(
        None,
        max_length=10,
        description="Replace attachment file IDs. Pass [] to clear (max 10).",
    )
    max_runtime_seconds: int | None = Field(
        None,
        ge=10,
        le=86400,
        description="Per-task timeout in seconds (10s–24h).",
    )
    completion_criteria: str | list[dict[str, str | int]] | None = Field(
        None,
        description=(
            "Acceptance criteria for completion verification. "
            "Plain string for semantic-only check, or structured list: "
            '[{"type": "shell", "command": "..."}, {"type": "semantic", "criteria": "..."}]'
        ),
    )
    result: str | None = Field(
        None,
        max_length=10000,
        description="Task result / handoff text. Typically edited post-completion to fix hallucinations.",
    )
    metadata: dict[str, object] | None = Field(
        None,
        description="Structured metadata to merge into task.metadata (e.g. changed_files, test_count).",
    )


class TaskMoveRequest(BaseModel):
    status: str
    force: bool = False
    block_kind: str | None = Field(None, description="Block sub-type: human / scheduled / external")
    blocked_reason: str | None = Field(None, max_length=1000)
    scheduled_until: datetime | None = Field(None, description="Auto-unblock time (ISO-8601) for scheduled blocks")
    result: str | None = Field(
        None,
        max_length=10000,
        description="Completion summary / handoff text. Persisted on task.result and on the synthetic run.",
    )
    metadata: dict[str, object] | None = Field(
        None,
        description="Structured handoff metadata (e.g. changed_files). Stored in task.metadata['handoff'].",
    )


class PromoteRequest(BaseModel):
    """Request body for promoting a BACKLOG task to READY."""

    force: bool = Field(
        False,
        description="If true, skip dependency check and promote immediately.",
    )
    reason: str | None = Field(
        None,
        max_length=500,
        description="Optional reason for force-promoting.",
    )


class UnmetParent(BaseModel):
    task_id: str
    title: str
    status: str


class PromoteResponse(BaseModel):
    """Response for a promote operation."""

    promoted: bool
    forced: bool = False
    reason: str | None = None
    unmet_parents: list[UnmetParent] = Field(default_factory=list)


class ReclaimRequest(BaseModel):
    """Request body for manually reclaiming a RUNNING task."""

    reason: str | None = Field(
        None,
        max_length=500,
        description="Human-readable reason for reclaiming the task.",
    )
    new_agent_id: str | None = Field(
        None,
        description="Optionally reassign to a different agent after reclaim.",
    )


class ReclaimResponse(BaseModel):
    """Response for a reclaim operation."""

    reclaimed: bool
    task: TaskResponse | None = None


class BulkActionRequest(BaseModel):
    """Batch lifecycle operation on multiple tasks."""

    task_ids: list[str] = Field(..., min_length=1, max_length=100)
    action: str = Field(
        ...,
        description="One of: move, archive, reassign, reclaim, delete",
    )
    params: dict[str, str] = Field(
        default_factory=dict,
        description="Action params: status (for move), agent_id (for reassign)",
    )
    confirm: bool = Field(
        False,
        description="Required for destructive actions (delete)",
    )


class BulkActionItemResult(BaseModel):
    task_id: str
    success: bool
    error: str | None = None


class BulkActionResponse(BaseModel):
    results: list[BulkActionItemResult]
    total: int
    succeeded: int
    failed: int


# ---------------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------------


class DiagnosticActionResponse(BaseModel):
    kind: str
    label: str
    payload: dict[str, str] = {}
    suggested: bool = False


class TaskDiagnosticResponse(BaseModel):
    rule_id: str
    severity: str
    title: str
    detail: str
    actions: list[DiagnosticActionResponse] = []


class DiagnosticSummaryResponse(BaseModel):
    """Lightweight summary embedded in TaskResponse for card badges."""

    count: int = 0
    max_severity: str | None = None


class TaskDiagnosticsResponse(BaseModel):
    """Full diagnostics for a single task (drawer-level)."""

    task_id: str
    diagnostics: list[TaskDiagnosticResponse] = []


# ---------------------------------------------------------------------------
# Task response
# ---------------------------------------------------------------------------


class AttachmentInfo(BaseModel):
    """Resolved attachment metadata for display."""

    file_id: str
    filename: str
    content_type: str
    url: str


class TaskResponse(BaseModel):
    task_id: str
    board_id: str
    title: str
    description: str
    status: str
    priority: str
    agent_id: str | None = None
    parent_task_id: str | None = None
    workspace_path: str | None = None
    branch: str | None = None
    retry_count: int = 0
    max_retries: int = 3
    consecutive_failures: int = 0
    blocked_reason: str | None = None
    block_kind: str | None = None
    scheduled_until: datetime | None = None
    progress_note: str | None = None
    result: str = ""
    error: str = ""
    metadata: dict[str, object] = {}
    extra_skill_ids: list[str] = []
    attachment_ids: list[str] = []
    attachments: list[AttachmentInfo] = []
    max_runtime_seconds: int | None = None
    completion_criteria: str | list[dict[str, str | int]] | None = None
    dep_count: int = 0
    children_total: int = 0
    children_done: int = 0
    comment_count: int = 0
    diagnostics_summary: DiagnosticSummaryResponse | None = None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None


class TaskListResponse(BaseModel):
    items: list[TaskResponse]
    total: int


class RunResponse(BaseModel):
    run_id: str
    task_id: str
    worker_id: str
    started_at: datetime
    ended_at: datetime | None = None
    outcome: str | None = None
    summary: str = ""
    error: str = ""
    duration_seconds: float | None = None


class EventResponse(BaseModel):
    event_id: int
    task_id: str
    kind: str
    payload: dict[str, object] | None = None
    run_id: str | None = None
    created_at: datetime


class RunListResponse(BaseModel):
    items: list[RunResponse]
    total: int


class EventListResponse(BaseModel):
    items: list[EventResponse]
    total: int


class BoardEventResponse(BaseModel):
    event_id: int
    task_id: str
    task_title: str = ""
    task_assignee: str = ""
    kind: str
    payload: dict[str, object] | None = None
    run_id: str | None = None
    created_at: str


class BoardEventListResponse(BaseModel):
    items: list[BoardEventResponse]
    total: int


class CommentCreate(BaseModel):
    body: str = Field(..., min_length=1, max_length=5000)
    author: str = Field(default="user", max_length=100)


class DependencyRequest(BaseModel):
    parent_task_id: str


class DependencyResponse(BaseModel):
    parent_task_id: str
    child_task_id: str


class DependencyListResponse(BaseModel):
    items: list[str]
    total: int


class EdgeListResponse(BaseModel):
    items: list[DependencyResponse]
    total: int


# ---------------------------------------------------------------------------
# Specify (TRIAGE → spec rewrite)
# ---------------------------------------------------------------------------


class ApplySpecRequest(BaseModel):
    """Body for POST /tasks/{task_id}/apply-spec — persists a cached preview."""

    new_title: str | None = None
    new_body: str = Field(..., min_length=1)
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


class SpecifyOutcomeResponse(BaseModel):
    """One Specifier pass result returned to the UI / SDK."""

    task_id: str
    ok: bool
    reason: str = ""
    new_title: str | None = None
    new_body: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    persisted: bool = False


class SpecifyAllResponse(BaseModel):
    """Batch Specify-all result for a board."""

    items: list[SpecifyOutcomeResponse]
    total: int
    persisted: bool


# ---------------------------------------------------------------------------
# Decompose (TRIAGE → child task graph)
# ---------------------------------------------------------------------------


class DecomposeChildResponse(BaseModel):
    """One proposed child task in a decompose preview."""

    title: str
    body: str
    assignee: str | None = None
    parent_indices: list[int] = []
    extra_skill_ids: list[str] = []


class DecomposeOutcomeResponse(BaseModel):
    """One Decomposer pass result returned to the UI."""

    task_id: str
    ok: bool
    fanout: bool = False
    children: list[DecomposeChildResponse] = []
    rationale: str = ""
    reason: str = ""
    new_title: str | None = None
    new_body: str | None = None
    new_assignee: str | None = None
    child_ids: list[str] = []
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    persisted: bool = False


class ApplyDecomposeRequest(BaseModel):
    """Body for POST /tasks/{task_id}/apply-decompose."""

    fanout: bool = True
    children: list[DecomposeChildResponse] = []
    new_title: str | None = None
    new_body: str | None = None
    new_assignee: str | None = None
    rationale: str = ""
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


# ---------------------------------------------------------------------------
# Pipeline Templates
# ---------------------------------------------------------------------------


class PipelineQuestionResponse(BaseModel):
    """A single discovery question."""

    id: str
    type: str
    label: str
    options: list[str] = []


class PipelineQuestionGroupResponse(BaseModel):
    """Grouped discovery questions."""

    group: str
    group_label: str
    questions: list[PipelineQuestionResponse]


class PipelineRoleResponse(BaseModel):
    """Role archetype within a pipeline."""

    role_id: str
    description: str
    required_skills: list[str] = []


class PipelineTaskSeedResponse(BaseModel):
    """A single task node in the pipeline graph template."""

    title_template: str
    description_template: str
    role: str
    parents: list[int] = []
    repeat_for: str | None = None


class PipelineTaskGraphVariantResponse(BaseModel):
    """A variant of the task graph."""

    id: str
    label: str
    description: str
    seeds: list[PipelineTaskSeedResponse] = []


class PipelineTemplateResponse(BaseModel):
    """Pipeline template summary for list view."""

    skill_id: str
    name: str
    description: str
    category: str
    tags: list[str] = []
    task_count: int = 0
    roles: list[str] = []


class PipelineTemplateDetailResponse(BaseModel):
    """Full pipeline template with discovery questions and task graph."""

    skill_id: str
    name: str
    description: str
    category: str
    tags: list[str] = []
    discovery_questions: list[PipelineQuestionGroupResponse] = []
    role_templates: list[PipelineRoleResponse] = []
    task_graph_seed: list[PipelineTaskSeedResponse] = []
    task_graph_variants: list[PipelineTaskGraphVariantResponse] = []


class PipelineTemplateListResponse(BaseModel):
    """List of available pipeline templates."""

    items: list[PipelineTemplateResponse]
    total: int


class PipelineInstantiateRequest(BaseModel):
    """Request body for instantiating a pipeline template."""

    skill_id: str = Field(..., min_length=1)
    answers: dict[str, str] = Field(default_factory=dict)
    variant_id: str | None = Field(None, description="Optional variant ID to select a specific task graph.")


class PipelineInstantiateResponse(BaseModel):
    """Result of pipeline instantiation."""

    task_ids: list[str]
    edges: list[list[str]] = []
    role_agent_mapping: dict[str, str | None] = {}
