"""[OUTPUT]
TaskCreate, TaskUpdate, TaskMoveRequest, PromoteRequest, UnmetParent, PromoteResponse, ReclaimRequest, ApproveTaskRequest, RejectTaskRequest, BulkActionRequest, BulkActionItemResult, BulkActionResponse

[POS]
Kanban task mutation schemas. Task create/update/move, promotion, reclaim, review and bulk lifecycle bodies.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class TaskCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)
    description: str = ""
    priority: str = "normal"
    parent_task_id: str | None = None
    agent_id: str | None = None
    model_override: str | None = Field(
        None,
        max_length=255,
        description=(
            "Per-task LLM model in 'provider/model' form. Overrides the agent "
            "profile default for this task only; sub-tasks inherit it."
        ),
    )
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
    goal_mode: bool = Field(
        False,
        description="Enable autonomous multi-turn execution until the task objective is met.",
    )
    goal_max_turns: int | None = Field(
        None,
        ge=1,
        le=100,
        description="Maximum turns for goal loop (1–100). Defaults to 10 when goal_mode is enabled.",
    )
    require_approval: bool = Field(
        False,
        description=(
            "When true, a successfully verified task lands in in_review and waits "
            "for a human approve/reject before it is marked completed."
        ),
    )
    initial_status: str | None = Field(
        None,
        description="Initial status: triage / backlog / ready / blocked. Defaults to backlog if depends_on, else ready.",
    )
    metadata: dict[str, object] | None = Field(
        None,
        description="Structured metadata merged into task.metadata (e.g. source_chat_id).",
    )


class TaskUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    priority: str | None = None
    agent_id: str | None = None
    model_override: str | None = Field(
        None,
        max_length=255,
        description="Replace the per-task model override. Pass null to inherit the agent profile default.",
    )
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
    require_approval: bool | None = Field(
        None,
        description=(
            "When true, a successfully verified task waits for human approval before "
            "completion. Only changeable while the task is active "
            "(TRIAGE/BACKLOG/READY/RUNNING/BLOCKED); rejected with 400 once the task "
            "enters IN_REVIEW or a terminal state."
        ),
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
    assignee_agent_id: str | None = Field(
        None,
        description="Agent ID to hand off / reassign this task to.",
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


class ApproveTaskRequest(BaseModel):
    """Body for approving an IN_REVIEW task (completion gate)."""

    approver: str | None = Field(
        None,
        max_length=100,
        description="Optional human identifier recorded on the approval event.",
    )


class RejectTaskRequest(BaseModel):
    """Body for rejecting an IN_REVIEW task (send back to READY for rework)."""

    reason: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="Why the task was rejected — injected into the re-run's context.",
    )
    approver: str | None = Field(
        None,
        max_length=100,
        description="Optional human identifier recorded on the rejection event.",
    )


class BulkActionRequest(BaseModel):
    """Batch lifecycle operation on multiple tasks."""

    task_ids: list[str] = Field(..., min_length=1, max_length=100)
    action: str = Field(
        ...,
        description="One of: move, archive, reassign, delete",
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
