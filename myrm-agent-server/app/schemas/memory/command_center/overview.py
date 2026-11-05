"""[INPUT]
- pydantic::BaseModel (POS: request/response model base)

[OUTPUT]
- MemoryCommandOverview, MemoryCommandSpace, MemoryCommandGovernanceItem, MemoryCommandHealth, MemoryCommandTimelineEvent, MemoryCommandPlaneSummary, MemoryCommandRuntimeStatus, MemoryCommandCenterResponse

[POS]
Memory command center schemas: command center overview, spaces, health, timeline and the top-level response.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from .diagnostics import (
    MemoryCommandConnectorStatus,
    MemoryCommandDoctorCheck,
    MemoryCommandEvalMetric,
    MemoryCommandPrivacySignal,
)
from .economics import MemoryCommandCostProfile, MemoryCommandEconomicsDashboard, MemoryCommandInfluenceItem
from .migration import MemoryCommandMigrationProvenance
from .replay import (
    MemoryCommandConflictItem,
    MemoryCommandReplayEvent,
    MemoryCommandReplayOverlay,
    MemoryCommandTraceRun,
    MemoryCommandWaterfallStep,
)


class MemoryCommandOverview(BaseModel):
    """Top-level memory system counters."""

    total_memories: int
    by_type: dict[str, int]
    pending_memories: int
    pending_shared_proposals: int
    active_shared_contexts: int
    health_score: int | None = None
    health_status: Literal["healthy", "degraded", "critical", "unknown"]
    deploy_mode: str


class MemoryCommandSpace(BaseModel):
    """Observable memory namespace or shared context."""

    namespace: str
    kind: str
    label: str
    target_id: str | None = None
    context_id: str | None = None
    active: bool = True
    binding_count: int = 0


class MemoryCommandGovernanceItem(BaseModel):
    """User-actionable memory governance item."""

    id: str
    kind: str
    target_kind: Literal["pending_memory", "shared_context_proposal", "memory", "conflict_pair"] = "memory"
    title: str
    description: str
    severity: Literal["info", "warning", "critical"] = "info"
    status: str
    created_at: datetime
    available_actions: list[str] = Field(default_factory=list)
    existing_value: str | None = None
    candidate_value: str | None = None
    confidence: float | None = None
    conflict_reason: str | None = None


class MemoryCommandHealth(BaseModel):
    """Memory health and guardian runtime status."""

    status: Literal["healthy", "degraded", "critical", "unknown"]
    total: int | None = None
    dimensions: dict[str, float] = Field(default_factory=dict)
    suggestions: list[str] = Field(default_factory=list)
    has_graph: bool = False
    sample_size: int = 0
    guardian_running: bool = False
    seconds_until_next: int | None = None
    checked_at: datetime | None = None
    cache_status: Literal["fresh", "refreshed", "unavailable"] = "unavailable"


class MemoryCommandTimelineEvent(BaseModel):
    """Recent memory activity derived from persisted business records."""

    id: str
    kind: str
    status: str
    occurred_at: datetime
    title: str
    description: str
    source: str
    memory_type: str | None = None
    namespace: str | None = None
    target_kind: str | None = None
    target_id: str | None = None
    influence_count: int = 0
    metadata: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class MemoryCommandPlaneSummary(BaseModel):
    """Content-free memory health summary safe for a control plane."""

    enabled: bool
    content_visibility: Literal["not_shared"]
    health_status: str
    import_rollback_health_status: Literal["ready", "warning", "critical"]
    archive_restore_health_status: Literal["ready", "warning", "critical"] = "ready"
    event_count: int
    failed_event_count: int
    queue_backlog: int
    import_rollback_in_progress: int = 0
    import_rollback_failed: int = 0
    import_rollback_partial: int = 0
    import_rollback_missing_items: int = 0
    import_rollback_failed_items: int = 0
    archive_restore_in_progress: int = 0
    archive_restore_failed: int = 0
    archive_restore_partial: int = 0
    archive_restore_rollback_in_progress: int = 0
    archive_restore_rollback_failed: int = 0
    archive_restore_missing_items: int = 0
    archive_restore_failed_items: int = 0
    last_event_at: datetime | None = None
    redaction_scope: Literal["metadata_only"]
    sandbox_isolation: Literal["local_or_per_user_sandbox"]


class MemoryCommandRuntimeStatus(BaseModel):
    """Deployment and storage status visible to the local memory UI."""

    deploy_mode: str
    memory_base_path: str
    relational_status: Literal["available", "unavailable"]
    vector_status: Literal["available", "unavailable"]
    vector_persistence: Literal["persistent", "memory_fallback", "unavailable"]
    graph_status: Literal["available", "unavailable"]
    embedding_status: Literal["custom", "unavailable"]
    retrieval_mode: Literal["semantic", "keyword"]
    control_plane_status: Literal["not_used", "proxied_by_sandbox"]
    event_ledger_status: Literal["available", "unavailable"]
    health_snapshot_status: Literal["available", "unavailable"]
    supported_clients: list[Literal["local_web", "tauri_desktop", "saas_sandbox"]] = Field(default_factory=list)


class MemoryCommandCenterResponse(BaseModel):
    """Aggregated snapshot for the personalized brain command center."""

    generated_at: datetime
    overview: MemoryCommandOverview
    spaces: list[MemoryCommandSpace]
    governance: list[MemoryCommandGovernanceItem]
    health: MemoryCommandHealth
    timeline: list[MemoryCommandTimelineEvent]
    live_stream: list[MemoryCommandTimelineEvent] = Field(default_factory=list)
    influence: list[MemoryCommandInfluenceItem] = Field(default_factory=list)
    cost: MemoryCommandCostProfile = Field(default_factory=MemoryCommandCostProfile)
    economics: MemoryCommandEconomicsDashboard | None = None
    conflicts: list[MemoryCommandConflictItem] = Field(default_factory=list)

    replay: list[MemoryCommandReplayOverlay] = Field(default_factory=list)
    replay_events: list[MemoryCommandReplayEvent] = Field(default_factory=list)
    waterfall: list[MemoryCommandWaterfallStep] = Field(default_factory=list)
    trace_runs: list[MemoryCommandTraceRun] = Field(default_factory=list)
    eval_metrics: list[MemoryCommandEvalMetric] = Field(default_factory=list)
    connectors: list[MemoryCommandConnectorStatus] = Field(default_factory=list)
    privacy: list[MemoryCommandPrivacySignal] = Field(default_factory=list)
    doctor_checks: list[MemoryCommandDoctorCheck] = Field(default_factory=list)
    migration: MemoryCommandMigrationProvenance
    plane_summary: MemoryCommandPlaneSummary
    runtime: MemoryCommandRuntimeStatus
