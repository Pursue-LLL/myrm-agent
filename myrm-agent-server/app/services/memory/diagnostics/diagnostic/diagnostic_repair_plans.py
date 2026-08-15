"""Memory Doctor repair plan catalog.

[INPUT]
app.schemas.memory.command_center::MemoryCommandDoctorCheck (POS: GUI diagnostic DTO)

[OUTPUT]
build_repair_plans, with_repair_plans: structured repair guidance for Memory Doctor.

[POS]
单用户 Memory Doctor 修复计划映射。只描述本地/沙箱内可执行性与风险，不修改配置、不读取业务记忆内容。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.schemas.memory.command_center import (
    MemoryCommandDiagnosticProbeResult,
    MemoryCommandDoctorCheck,
    MemoryCommandRepairPlan,
)

RepairRiskLevel = Literal["safe", "confirmation_required", "manual"]


@dataclass(frozen=True)
class _RepairPlanSpec:
    label: str
    risk_level: RepairRiskLevel
    dry_run_result: str
    expected_effect: str
    requires_confirmation: bool = False
    executable: bool = False


_REPAIR_PLAN_CATALOG: dict[str, _RepairPlanSpec] = {
    "run_diagnostics": _RepairPlanSpec(
        label="Run diagnostics",
        risk_level="safe",
        dry_run_result="Executes read-only probes plus content-free audit events.",
        expected_effect="Refreshes probe evidence and confirms whether dependencies recovered.",
        executable=True,
    ),
    "run_health_refresh": _RepairPlanSpec(
        label="Refresh health snapshot",
        risk_level="safe",
        dry_run_result="Recomputes local memory quality metrics and updates the health cache.",
        expected_effect="Updates freshness, coverage, retention, and coherence signals shown in the GUI.",
        executable=True,
    ),
    "review_storage_config": _RepairPlanSpec(
        label="Review storage configuration",
        risk_level="manual",
        dry_run_result="Checks point to a local storage, database, or permission issue.",
        expected_effect="Restores persistence for memory writes, replay events, and diagnostics after operator action.",
    ),
    "enable_vector_store": _RepairPlanSpec(
        label="Enable vector store",
        risk_level="confirmation_required",
        dry_run_result="Vector-backed semantic and episodic recall is unavailable or degraded.",
        expected_effect="Restores high-recall semantic search after vector storage and embeddings are configured.",
        requires_confirmation=True,
    ),
    "configure_embedding": _RepairPlanSpec(
        label="Configure embedding provider",
        risk_level="confirmation_required",
        dry_run_result="Embedding checks failed or no embedding provider is configured.",
        expected_effect="Allows new memories to be embedded, indexed, and recalled by semantic similarity.",
        requires_confirmation=True,
    ),
    "review_retrieval_trace": _RepairPlanSpec(
        label="Review retrieval trace",
        risk_level="safe",
        dry_run_result="Uses existing trace metadata without exposing retrieved memory content.",
        expected_effect="Identifies which retrieval stage stopped producing trace or recall evidence.",
    ),
    "reindex_memories": _RepairPlanSpec(
        label="Reindex orphan memories",
        risk_level="confirmation_required",
        dry_run_result="Memories from previous embedding models exist in orphan collections.",
        expected_effect="Re-embeds orphan memories with the current model, restoring full recall coverage.",
        requires_confirmation=True,
        executable=True,
    ),
}


def build_repair_plans(actions: list[str]) -> list[MemoryCommandRepairPlan]:
    """Map compact action ids to structured GUI repair plans."""

    plans: list[MemoryCommandRepairPlan] = []
    for action in actions:
        spec = _REPAIR_PLAN_CATALOG.get(action)
        if spec is None:
            continue
        plans.append(
            MemoryCommandRepairPlan(
                id=action,
                label=spec.label,
                risk_level=spec.risk_level,
                dry_run_result=spec.dry_run_result,
                expected_effect=spec.expected_effect,
                requires_confirmation=spec.requires_confirmation,
                executable=spec.executable,
            )
        )
    return plans


def with_check_repair_plans(check: MemoryCommandDoctorCheck) -> MemoryCommandDoctorCheck:
    """Attach structured repair plans to a static doctor check."""

    return check.model_copy(update={"repair_plans": build_repair_plans(check.repair_actions)})


def with_probe_repair_plans(probe: MemoryCommandDiagnosticProbeResult) -> MemoryCommandDiagnosticProbeResult:
    """Attach structured repair plans to an executable probe result."""

    return probe.model_copy(update={"repair_plans": build_repair_plans(probe.repair_actions)})
