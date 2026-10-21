"""Runtime Console & Multi-Surface Run Projection Data Contracts.

[INPUT]
- pydantic: BaseModel, Field
- typing: Literal

[OUTPUT]
- SurfaceViewType: Four primary projection surfaces (chat, runtime_console, deliverables, audit)
- AttemptStatus: State lifecycle for individual execution attempts
- AttemptRecord: Telemetry, duration, token throughput, and fault diagnostic for an attempt
- RunProjectionEvent: Monotonic append-only event item
- DeliverableItem: Concrete deliverable fact tracked in Run
- AuditLedgerEntry: Compliance & permission authorization entry
- RunStateSnapshot: Immutable single source of truth for pure functional rendering

[POS]
app/services/runs/projection/projection_types.py: Core Pydantic contracts implementing
MateClaw parity (UI = Project(RunState, Events)).
"""

from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field

SurfaceViewType = Literal["chat", "runtime_console", "deliverables", "audit"]
AttemptStatus = Literal["pending", "executing", "completed", "failed", "retrying"]


class AttemptRecord(BaseModel):
    """Detailed telemetry and diagnostic record for a single execution attempt."""

    attempt_id: str = Field(..., description="Unique attempt trace ID")
    run_id: str = Field(..., description="Parent run ID")
    attempt_number: int = Field(..., description="1-indexed sequence number of this attempt")
    status: AttemptStatus = Field(default="executing", description="Current execution state")
    started_at_ms: int = Field(..., description="Attempt start timestamp epoch milliseconds")
    finished_at_ms: int | None = Field(default=None, description="Attempt completion timestamp epoch milliseconds")
    duration_ms: int | None = Field(default=None, description="Elapsed execution duration in milliseconds")
    tokens_in: int = Field(default=0, description="Input prompt token count")
    tokens_out: int = Field(default=0, description="Generated output token count")
    tokens_per_sec: float = Field(default=0.0, description="Real-time generation throughput rate")
    error_reason: str | None = Field(default=None, description="Structured failure reason or exception message")
    stack_trace: str | None = Field(default=None, description="Diagnostic stack trace if failed")
    diff_summary: str | None = Field(default=None, description="Workspace mutation summary or virtual diff count")


class RunProjectionEvent(BaseModel):
    """Monotonic event emitted into the run projection log."""

    event_id: str = Field(..., description="Unique event identifier")
    run_id: str = Field(..., description="Parent run ID")
    event_type: str = Field(..., description="Categorized event action name")
    timestamp_ms: int = Field(..., description="Event emission timestamp epoch milliseconds")
    payload: dict[str, object] = Field(default_factory=dict, description="Structured event payload")


class DeliverableItem(BaseModel):
    """Artifact or deliverable fact tracked by the run."""

    deliverable_id: str = Field(..., description="Unique deliverable identifier")
    title: str = Field(..., description="Deliverable display title")
    type: str = Field(..., description="File or artifact classification")
    path_or_uri: str = Field(..., description="Relative filesystem path or external URI")
    status: str = Field(default="verified", description="Verification state of the deliverable")
    created_at_ms: int = Field(..., description="Creation epoch timestamp in milliseconds")


class AuditLedgerEntry(BaseModel):
    """Compliance audit ledger entry for security oversight."""

    audit_id: str = Field(..., description="Unique audit trace identifier")
    action: str = Field(..., description="Security action name (e.g. bash_execution, tool_call)")
    actor: str = Field(..., description="Identity invoking the action")
    risk_level: str = Field(default="low", description="Risk tier classification: low, medium, high")
    decision: str = Field(default="approved", description="Policy decision: approved, blocked, prompted")
    timestamp_ms: int = Field(..., description="Audit record epoch timestamp in milliseconds")


class RunStateSnapshot(BaseModel):
    """Complete, immutable projection snapshot for pure functional UI rendering."""

    run_id: str = Field(..., description="Unique run identifier")
    title: str = Field(..., description="Run task objective title")
    status: str = Field(default="running", description="Overall execution status")
    active_surface: SurfaceViewType = Field(default="chat", description="Currently focused projection surface")
    current_attempt: int = Field(default=1, description="Latest attempt sequence number")
    attempts: list[AttemptRecord] = Field(default_factory=list, description="All historic and active attempts")
    deliverables: list[DeliverableItem] = Field(default_factory=list, description="Produced deliverables matrix")
    audit_entries: list[AuditLedgerEntry] = Field(default_factory=list, description="Security and permission entries")
    events: list[RunProjectionEvent] = Field(default_factory=list, description="Monotonic event history")
    total_tokens: int = Field(default=0, description="Accumulated tokens across all attempts")
    avg_tokens_per_sec: float = Field(default=0.0, description="Average token generation throughput")
