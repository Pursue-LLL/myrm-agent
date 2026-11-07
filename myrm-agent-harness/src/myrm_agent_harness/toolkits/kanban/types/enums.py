"""[INPUT]
- （标准库 enum）

[OUTPUT]
- TaskStatus / BlockKind / TaskPriority / TaskRunOutcome / TaskEventKind / TaskExecutionOutcome
- 由状态派生的终态、活动态、分类转移与优先级顺序集合

[POS]
`kanban/types/` 的枚举与派生集合；不依赖任何模型。
"""

from __future__ import annotations

from enum import StrEnum


class TaskStatus(StrEnum):
    """Kanban task lifecycle states.

    State machine::

        TRIAGE ──► BACKLOG ──► READY ──► RUNNING ──► IN_REVIEW ──► COMPLETED
           │          │           │          │         │ (approve)
           │          │           │          │         │
           │          │           │          ├──► FAILED
           │          │           │          │
           │          │           │          └──► BLOCKED
           │          │           │
           └──────────┴───────────┴──► ARCHIVED

    TRIAGE is the inbox for rough ideas pending LLM-driven Specifier rewrite.
    A TRIAGE task is opaque to the dispatcher (never claimed) — it can only
    transition to BACKLOG/READY (via specify) or to ARCHIVED (manual discard).

    IN_REVIEW is the human-approval gate for tasks created with
    ``require_approval=True``. The dispatcher lands a successfully verified
    task in IN_REVIEW (never COMPLETED) until an operator approves it
    (→ COMPLETED, then dependents are promoted) or rejects it (→ READY for
    rework). Approval is operator-driven via REST/GUI — no LLM tool.
    """

    TRIAGE = "triage"
    BACKLOG = "backlog"
    READY = "ready"
    RUNNING = "running"
    BLOCKED = "blocked"
    IN_REVIEW = "in_review"
    COMPLETED = "completed"
    FAILED = "failed"
    ARCHIVED = "archived"

_TERMINAL_STATUSES: frozenset[TaskStatus] = frozenset({TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.ARCHIVED})

_ACTIVE_STATUSES: frozenset[TaskStatus] = frozenset(
    {TaskStatus.READY, TaskStatus.RUNNING, TaskStatus.BLOCKED, TaskStatus.IN_REVIEW}
)

_TRIAGE_ALLOWED_TARGETS: frozenset[TaskStatus] = frozenset({TaskStatus.BACKLOG, TaskStatus.READY, TaskStatus.ARCHIVED})

class BlockKind(StrEnum):
    """Sub-type for BLOCKED tasks — distinguishes *why* a task is blocked.

    HUMAN: waiting for a human decision (e.g. PR review, manual approval).
    SCHEDULED: waiting for a specific time — dispatcher auto-unblocks when due.
    EXTERNAL: waiting for an external event (e.g. CI/CD pipeline, webhook).
    """

    HUMAN = "human"
    SCHEDULED = "scheduled"
    EXTERNAL = "external"

class TaskPriority(StrEnum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"

_PRIORITY_ORDER: dict[TaskPriority, int] = {
    TaskPriority.URGENT: 0,
    TaskPriority.HIGH: 1,
    TaskPriority.NORMAL: 2,
    TaskPriority.LOW: 3,
}

class TaskRunOutcome(StrEnum):
    """Outcome classification for a completed run."""

    COMPLETED = "completed"
    BLOCKED = "blocked"
    CRASHED = "crashed"
    TIMED_OUT = "timed_out"
    RECLAIMED = "reclaimed"

class TaskEventKind(StrEnum):
    """Lifecycle event categories."""

    CREATED = "created"
    CLAIMED = "claimed"
    ASSIGNED = "assigned"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"
    UNBLOCKED = "unblocked"
    RETRYING = "retrying"
    RECLAIMED = "reclaimed"
    PROMOTED = "promoted"
    ARCHIVED = "archived"
    HEARTBEAT = "heartbeat"
    USER_COMMENT = "user_comment"
    VERIFICATION_FAILED = "verification_failed"
    BRANCH_SWITCHED = "branch_switched"
    MERGE_CONFLICT = "merge_conflict"
    SPECIFIED = "specified"
    DECOMPOSED = "decomposed"
    TIMED_OUT = "timed_out"
    COMPLETION_REQUESTED = "completion_requested"
    EDITED = "edited"
    REVIEW_REQUESTED = "review_requested"
    APPROVED = "approved"
    REJECTED = "rejected"
    PLAN_REVISED = "plan_revised"
    RACE_STARTED = "race_started"
    RACE_DECIDED = "race_decided"

class TaskExecutionOutcome(StrEnum):
    """Structured outcome for TaskRunner execution."""

    SUCCESS = "success"
    BLOCKED = "blocked"
    FAILURE = "failure"
