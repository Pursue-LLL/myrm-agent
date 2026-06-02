"""Personal memory command center API schemas.

[INPUT]
pydantic::BaseModel (POS: 请求/响应模型基类)

[OUTPUT]
MemoryCommandCenterResponse and nested command center response models.

[POS]
记忆指挥中心 API Schema 层。定义单用户/单沙箱记忆控制台的 HTTP 响应契约。
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from myrm_agent_harness.toolkits.memory import MemoryRepairExecutionResult
from pydantic import BaseModel, Field


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
    target_kind: Literal["pending_memory", "shared_context_proposal", "memory"] = "memory"
    title: str
    description: str
    severity: Literal["info", "warning", "critical"] = "info"
    status: str
    created_at: datetime
    available_actions: list[str] = Field(default_factory=list)


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


class MemoryCommandInfluenceRef(BaseModel):
    """A memory reference that influenced an answer or runtime decision."""

    memory_id: str
    memory_type: str
    score: float | None = None
    content_preview: str = ""
    primary_namespace: str | None = None
    source_chat_id: str | None = None
    source_message_id: str | None = None
    reason: str | None = None


class MemoryCommandInfluenceItem(BaseModel):
    """Message-level memory influence evidence."""

    id: str
    chat_id: str | None = None
    message_id: str | None = None
    occurred_at: datetime
    answer_preview: str = ""
    influence_refs: list[MemoryCommandInfluenceRef] = Field(default_factory=list)
    prompt_tokens: int = 0
    cached_tokens: int = 0


class MemoryCommandCostProfile(BaseModel):
    """Prompt injection and cache impact summary."""

    prompt_tokens: int = 0
    cached_tokens: int = 0
    completion_tokens: int = 0
    cited_memory_refs: int = 0
    estimated_memory_tokens: int = 0
    cache_friendly: bool = True


class MemoryCommandConflictItem(BaseModel):
    """Claim, correction, and supersession visibility item."""

    id: str
    kind: Literal["claim", "correction", "supersession"]
    status: Literal["active", "needs_review", "resolved"]
    memory_id: str | None = None
    related_memory_id: str | None = None
    title: str
    description: str
    created_at: datetime | None = None


class MemoryCommandReplayOverlay(BaseModel):
    """Session replay overlay index for memory events."""

    chat_id: str
    message_id: str | None = None
    event_count: int
    influence_count: int
    last_event_at: datetime
    last_summary: str


class MemoryCommandReplayEvent(BaseModel):
    """One normalized event for the replay timeline."""

    id: str
    phase: Literal["observe", "govern", "write", "index", "recall", "inject", "verify"]
    status: str
    occurred_at: datetime
    title: str
    summary: str
    target_kind: str | None = None
    target_id: str | None = None
    correlation_id: str | None = None
    influence_count: int = 0


class MemoryCommandWaterfallStep(BaseModel):
    """Aggregated memory operation waterfall step."""

    phase: Literal["observe", "scan", "propose", "approve", "write", "index", "recall", "inject", "cite", "verify"]
    status: Literal["ready", "active", "warning", "missing"]
    event_count: int = 0
    evidence_count: int = 0
    latest_at: datetime | None = None
    description: str


class MemoryCommandTraceStep(BaseModel):
    """One persisted retrieval trace step within a memory recall run."""

    id: str
    phase: str
    status: Literal["success", "warning", "error", "skipped"]
    title: str
    description: str
    occurred_at: datetime
    duration_ms: float | None = None
    output_count: int = 0
    result_count: int = 0
    step_index: int = 0


class MemoryCommandTraceRun(BaseModel):
    """A grouped memory retrieval trace run for the command center UI."""

    id: str
    trace_id: str
    message_id: str | None = None
    chat_id: str | None = None
    query_preview: str = ""
    status: Literal["success", "warning", "error", "skipped"]
    occurred_at: datetime
    duration_ms: float | None = None
    result_count: int = 0
    steps: list[MemoryCommandTraceStep] = Field(default_factory=list)


class MemoryCommandEvalMetric(BaseModel):
    """Memory quality readiness metric shown in the command center."""

    id: str
    label: str
    status: Literal["ready", "partial", "missing"]
    score: int
    evidence: str


class MemoryCommandConnectorStatus(BaseModel):
    """External agent connector readiness without CLI-first coupling."""

    id: str
    label: str
    status: Literal["ready", "manual_config_required", "missing"]
    supported_actions: list[str] = Field(default_factory=list)
    notes: str = ""


class MemoryCommandPrivacySignal(BaseModel):
    """Privacy and secret-governance signal."""

    id: str
    label: str
    status: Literal["ready", "warning", "missing"]
    evidence: str
    event_count: int = 0


class MemoryCommandRepairPlan(BaseModel):
    """Structured Memory Doctor repair guidance surfaced by the GUI."""

    id: str
    label: str
    risk_level: Literal["safe", "confirmation_required", "manual"]
    dry_run_result: str
    expected_effect: str
    requires_confirmation: bool = False
    executable: bool = False


class MemoryCommandDoctorCheck(BaseModel):
    """Runtime memory doctor check shown in the local command center."""

    id: str
    category: Literal["storage", "index", "embedding", "ledger", "deployment", "quality", "migration"]
    label: str
    status: Literal["ready", "warning", "critical", "missing"]
    evidence: str
    impact: str = ""
    next_action: str = ""
    can_auto_fix: bool = False
    safe_to_retry: bool = True
    docs_ref: str | None = None
    repair_actions: list[str] = Field(default_factory=list)
    repair_plans: list[MemoryCommandRepairPlan] = Field(default_factory=list)


class MemoryCommandBenchmarkSummary(BaseModel):
    """Structured recall benchmark metrics for frontend rendering."""

    case_count: int = 0
    passed_count: int = 0
    recall_at_k: float = 0.0
    ndcg_at_k: float = 0.0
    mrr_score: float = 0.0
    precision_at_k: float = 0.0
    latency_p50_ms: float = 0.0
    latency_p95_ms: float = 0.0
    top_k: int = 5
    categories: dict[str, str] = Field(default_factory=dict)


class MemoryCommandDiagnosticProbeResult(BaseModel):
    """Single probe result from an executable memory diagnostic run."""

    id: str
    category: Literal["storage", "index", "embedding", "ledger", "deployment", "quality", "migration"]
    label: str
    status: Literal["ready", "warning", "critical", "missing"]
    evidence: str
    impact: str = ""
    next_action: str = ""
    can_auto_fix: bool = False
    safe_to_retry: bool = True
    docs_ref: str | None = None
    duration_ms: float | None = None
    benchmark_summary: MemoryCommandBenchmarkSummary | None = None
    repair_actions: list[str] = Field(default_factory=list)
    repair_plans: list[MemoryCommandRepairPlan] = Field(default_factory=list)


class MemoryCommandDiagnosticSlo(BaseModel):
    """Content-free diagnostic reliability rollup from recent audit events."""

    window_runs: int = 0
    pass_rate: float = 0.0
    failed_runs: int = 0
    average_duration_ms: float = 0.0
    status: Literal["ready", "warning", "critical", "missing"] = "missing"


class MemoryCommandDiagnosticRun(BaseModel):
    """Executable Memory Doctor run with probe-level evidence."""

    id: str
    status: Literal["ready", "warning", "critical", "missing"]
    summary: str = ""
    started_at: datetime
    completed_at: datetime
    duration_ms: float
    probe_count: int
    failed_count: int
    audit_recorded: bool = False
    audit_error: str | None = None
    slo: MemoryCommandDiagnosticSlo | None = None
    probes: list[MemoryCommandDiagnosticProbeResult] = Field(default_factory=list)


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
    storage_mode: str
    last_event_at: datetime | None = None
    redaction_scope: Literal["metadata_only"]
    sandbox_isolation: Literal["local_or_per_user_sandbox"]


class MemoryCommandMigrationProvenance(BaseModel):
    """Import/export provenance summary for memory migration visibility."""

    supported_sources: list[str]
    tracked_imports: int = 0
    unmapped_items: int = 0
    coverage_status: Literal["not_tracked", "partial", "complete"] = "not_tracked"
    adapter_status: dict[str, Literal["ready", "planned", "missing"]] = Field(default_factory=dict)
    last_import_batch_id: str | None = None
    verification_recommended: bool = False
    last_import_diagnostic_status: str | None = None
    last_import_diagnostic_run_id: str | None = None
    cleanup_pending_sessions: int = 0
    cleanup_confirmed_sessions: int = 0
    cleanup_expired_sessions: int = 0
    cleanup_rolled_back_sessions: int = 0
    cleanup_retention_days: int = 7


class MemoryCommandRuntimeStatus(BaseModel):
    """Deployment and storage status visible to the local memory UI."""

    deploy_mode: str
    storage_mode: str
    memory_base_path: str
    relational_status: Literal["available", "unavailable"]
    vector_status: Literal["available", "unavailable"]
    graph_status: Literal["available", "unavailable"]
    embedding_status: Literal["custom", "unavailable"]
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


class MemoryCommandGraphNode(BaseModel):
    """Graph node for claim graph visualization."""

    id: str
    labels: list[str] = Field(default_factory=list)
    properties: dict[str, str | int | float | bool] = Field(default_factory=dict)


class MemoryCommandGraphEdge(BaseModel):
    """Graph edge (relationship) for claim graph visualization."""

    id: str
    source: str
    target: str
    rel_type: str
    properties: dict[str, str | int | float] = Field(default_factory=dict)


class MemoryCommandGraphStats(BaseModel):
    """Graph aggregate statistics."""

    node_count: int = 0
    relationship_count: int = 0
    node_label_counts: dict[str, int] = Field(default_factory=dict)
    relationship_type_counts: dict[str, int] = Field(default_factory=dict)


class MemoryCommandGraphResponse(BaseModel):
    """Knowledge Graph visualization data for the command center."""

    nodes: list[MemoryCommandGraphNode] = Field(default_factory=list)
    edges: list[MemoryCommandGraphEdge] = Field(default_factory=list)
    stats: MemoryCommandGraphStats = Field(default_factory=MemoryCommandGraphStats)
    has_graph: bool = False


class MemoryCommandActionRequest(BaseModel):
    """Command center governance action request."""

    target_kind: Literal["pending_memory", "shared_context_proposal", "memory"]
    target_id: str
    action: Literal["approve", "reject", "edit", "correct", "forget", "pin", "unpin"]
    memory_type: str | None = None
    content: str | None = None


class MemoryCommandActionResponse(BaseModel):
    """Command center governance action result."""

    status: Literal["success"]
    target_kind: str
    target_id: str
    action: str


class MemoryCommandDiagnosticActionRequest(BaseModel):
    """Executable Memory Doctor action request."""

    action: Literal["run_diagnostics", "run_health_refresh"]


class MemoryCommandDiagnosticActionResponse(BaseModel):
    """Executable Memory Doctor action result."""

    status: Literal["completed", "completed_with_findings", "failed"]
    action: str
    run: MemoryCommandDiagnosticRun


class MemoryCommandRepairActionRequest(BaseModel):
    """Structured Memory Doctor repair execution request."""

    plan_id: Literal[
        "run_diagnostics",
        "run_health_refresh",
        "review_storage_config",
        "enable_vector_store",
        "configure_embedding",
        "review_retrieval_trace",
    ]
    mode: Literal["dry_run", "execute"] = "execute"


class MemoryCommandRepairActionResponse(BaseModel):
    """Structured Memory Doctor repair execution result."""

    result: MemoryRepairExecutionResult
    run: MemoryCommandDiagnosticRun | None = None
