"""[INPUT]
- pydantic::BaseModel (POS: request/response model base)

[OUTPUT]
- MemoryCommandEvalMetric, MemoryCommandConnectorStatus, MemoryCommandPrivacySignal, MemoryCommandRepairPlan, MemoryCommandDoctorCheck, MemoryCommandBenchmarkSummary, MemoryCommandDiagnosticProbeResult, MemoryCommandDiagnosticSlo, MemoryCommandDiagnosticRun, MemoryCommandDiagnosticHistoryItem, MemoryCommandDiagnosticHistoryResponse

[POS]
Memory command center schemas: doctor checks, probes, benchmark summaries and repair plans.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


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
    category: Literal["storage", "index", "embedding", "ledger", "deployment", "quality", "migration", "governance"]
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
    duplicate_rate: float = 0.0
    distinct_source_ratio: float = 1.0
    latency_p50_ms: float = 0.0
    latency_p95_ms: float = 0.0
    latency_p99_ms: float = 0.0
    top_k: int = 5
    categories: dict[str, str] = Field(default_factory=dict)


class MemoryCommandDiagnosticProbeResult(BaseModel):
    """Single probe result from an executable memory diagnostic run."""

    id: str
    category: Literal["storage", "index", "embedding", "ledger", "deployment", "quality", "migration", "governance"]
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


class MemoryCommandDiagnosticHistoryItem(BaseModel):
    """One historical diagnostic run with persisted golden recall benchmark metrics."""

    run_id: str
    status: Literal["ready", "warning", "critical", "missing"]
    occurred_at: datetime
    duration_ms: float
    probe_count: int
    failed_count: int
    benchmark: MemoryCommandBenchmarkSummary | None = None
    embedding_model: str | None = None


class MemoryCommandDiagnosticHistoryResponse(BaseModel):
    """Chronological diagnostic history for Memory Doctor trend rendering."""

    items: list[MemoryCommandDiagnosticHistoryItem] = Field(default_factory=list)
