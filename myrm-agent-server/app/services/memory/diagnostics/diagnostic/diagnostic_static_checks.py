"""Static Memory Doctor checks.

[INPUT]
app.schemas.memory.command_center::MemoryCommandRuntimeStatus (POS: deployment and storage status)

[OUTPUT]
Static MemoryCommandDoctorCheck builders for snapshot rendering.

[POS]
单用户记忆静态诊断检查。只读取运行时状态和本地路径权限，不访问业务记忆内容。
"""

from __future__ import annotations

import os
from pathlib import Path

from app.schemas.memory.command_center import MemoryCommandDoctorCheck, MemoryCommandRuntimeStatus

DiagnosticStatus = str


def probe_relational_store(
    runtime: MemoryCommandRuntimeStatus,
    *,
    integrity_ok: bool = True,
    integrity_detail: str = "ok",
) -> MemoryCommandDoctorCheck:
    if not integrity_ok:
        status: DiagnosticStatus = "critical"
        evidence = f"Relational memory store failed integrity verification: {integrity_detail}."
        next_action = "Database is corrupted. Restore from backup or reset memory store."
        repair_actions = ["restore_from_backup", "review_storage_config"]
    elif runtime.relational_status != "available":
        status = "critical"
        evidence = f"Relational memory store is {runtime.relational_status}."
        next_action = "Review the SQLite database path and permissions."
        repair_actions = ["review_storage_config"]
    else:
        status = "ready"
        evidence = "Relational memory store is available and passed integrity verification."
        next_action = "No action required."
        repair_actions = []

    return MemoryCommandDoctorCheck(
        id="relational_store",
        category="storage",
        label="Relational store",
        status=status,
        evidence=evidence,
        impact="Profile, procedural, governance, and audit data depend on the relational store.",
        next_action=next_action,
        repair_actions=repair_actions,
    )


def probe_memory_base_path(runtime: MemoryCommandRuntimeStatus) -> MemoryCommandDoctorCheck:
    path = Path(runtime.memory_base_path).expanduser()
    writable_path = path if path.exists() else path.parent
    is_writable = writable_path.exists() and os.access(writable_path, os.W_OK)
    status: DiagnosticStatus = "ready" if is_writable else "critical"
    repair_actions: list[str] = [] if is_writable else ["review_storage_config"]
    return MemoryCommandDoctorCheck(
        id="memory_base_path",
        category="storage",
        label="Memory base path",
        status=status,
        evidence=f"Memory base path is {path}; writable parent check is {'available' if is_writable else 'unavailable'}.",
        impact="Local Web, Tauri desktop, and sandbox deployments need this path to persist memory files.",
        next_action="No action required." if is_writable else "Grant write permission or update the memory base path.",
        repair_actions=repair_actions,
    )


def probe_vector_index(runtime: MemoryCommandRuntimeStatus) -> MemoryCommandDoctorCheck:
    memory_fallback = runtime.vector_persistence == "memory_fallback"
    status: DiagnosticStatus
    if memory_fallback:
        status = "warning"
    elif runtime.vector_status == "available":
        status = "ready"
    else:
        status = "missing"
    evidence = (
        "Vector recall backend is available but degraded to an in-memory instance."
        if memory_fallback
        else f"Vector recall backend is {runtime.vector_status}."
    )
    impact = (
        "Semantic and episodic memories need vector search for high-recall cross-session retrieval."
        if not memory_fallback
        else "The embedded vector store degraded to an in-memory instance: new memories will be lost on restart."
    )
    next_action = (
        "No action required."
        if status == "ready"
        else (
            "Restore a writable memory storage path and restart the service so memories persist again."
            if memory_fallback
            else "Enable vector storage and configure embeddings."
        )
    )
    repair_actions: list[str]
    if status == "ready":
        repair_actions = []
    elif memory_fallback:
        repair_actions = ["review_storage_config", "run_diagnostics"]
    else:
        repair_actions = ["enable_vector_store", "configure_embedding"]
    return MemoryCommandDoctorCheck(
        id="vector_index",
        category="index",
        label="Vector index",
        status=status,
        evidence=evidence,
        impact=impact,
        next_action=next_action,
        repair_actions=repair_actions,
    )


def probe_knowledge_graph(runtime: MemoryCommandRuntimeStatus) -> MemoryCommandDoctorCheck:
    return MemoryCommandDoctorCheck(
        id="knowledge_graph",
        category="index",
        label="Knowledge graph",
        status="ready" if runtime.graph_status == "available" else "warning",
        evidence=f"Graph relationship recall is {runtime.graph_status}.",
        impact="Graph recall strengthens relationship reasoning and replay explanations.",
        next_action="No action required."
        if runtime.graph_status == "available"
        else "Enable graph storage when relationship recall is required.",
        repair_actions=[] if runtime.graph_status == "available" else ["review_storage_config"],
    )


def probe_embedding_provider(runtime: MemoryCommandRuntimeStatus) -> MemoryCommandDoctorCheck:
    embedding_ready = runtime.embedding_status != "unavailable"
    return MemoryCommandDoctorCheck(
        id="embedding_provider",
        category="embedding",
        label="Embedding provider",
        status="ready" if embedding_ready else "critical",
        evidence=f"Embedding mode is {runtime.embedding_status}.",
        impact="Embeddings are required for vector indexing, hybrid recall, and semantic memory continuity.",
        next_action="No action required." if embedding_ready else "Configure a valid embedding provider.",
        repair_actions=[] if embedding_ready else ["configure_embedding"],
    )


def probe_event_ledger_snapshot(runtime: MemoryCommandRuntimeStatus) -> MemoryCommandDoctorCheck:
    return MemoryCommandDoctorCheck(
        id="event_ledger",
        category="ledger",
        label="Event ledger",
        status="ready" if runtime.event_ledger_status == "available" else "critical",
        evidence=f"Command Center event ledger is {runtime.event_ledger_status}.",
        impact="The UI needs ledger events for audit trails, waterfall views, and replay overlays.",
        next_action="No action required."
        if runtime.event_ledger_status == "available"
        else "Review local database configuration.",
        repair_actions=[] if runtime.event_ledger_status == "available" else ["review_storage_config"],
    )


def probe_health_snapshot(health_cache_status: str) -> MemoryCommandDoctorCheck:
    is_ready = health_cache_status in {"fresh", "refreshed"}
    return MemoryCommandDoctorCheck(
        id="health_snapshot",
        category="ledger",
        label="Health snapshot",
        status="ready" if is_ready else "warning",
        evidence=f"Memory health cache is {health_cache_status}.",
        impact="Fresh health snapshots keep the UI responsive while still surfacing memory quality drift.",
        next_action="No action required." if is_ready else "Refresh the health snapshot.",
        can_auto_fix=not is_ready,
        repair_actions=[] if is_ready else ["run_health_refresh"],
    )


def probe_deployment_boundary(runtime: MemoryCommandRuntimeStatus) -> MemoryCommandDoctorCheck:
    return MemoryCommandDoctorCheck(
        id="deployment_boundary",
        category="deployment",
        label="Deployment boundary",
        status="ready",
        evidence=(
            f"Supported clients: {', '.join(runtime.supported_clients)}; control plane status: {runtime.control_plane_status}."
        ),
        impact="Business memory content stays inside the local or per-user sandbox boundary.",
        next_action="No action required.",
        repair_actions=[],
    )


def probe_orphan_collections(orphan_count: int, old_models: list[str]) -> MemoryCommandDoctorCheck:
    has_orphans = orphan_count > 0
    model_list = ", ".join(old_models[:3]) if old_models else ""
    return MemoryCommandDoctorCheck(
        id="orphan_collections",
        category="embedding",
        label="Orphan collections",
        status="warning" if has_orphans else "ready",
        evidence=(
            f"Found {orphan_count} memories in collections from previous models ({model_list})."
            if has_orphans
            else "No orphan collections detected."
        ),
        impact="Memories in orphan collections are invisible to recall until re-embedded with the current model.",
        next_action=("Reindex orphan memories to restore recall coverage." if has_orphans else "No action required."),
        repair_actions=["reindex_memories"] if has_orphans else [],
    )


def probe_context_bundle_manifest(runtime: MemoryCommandRuntimeStatus) -> MemoryCommandDoctorCheck:
    from myrm_agent_harness.toolkits.context_bundle import run_migration_dry_run

    memory_path = Path(runtime.memory_base_path).expanduser()
    state_dir = memory_path.parent if memory_path.name == "memory" else memory_path
    report = run_migration_dry_run(state_dir)

    status: DiagnosticStatus = "ready" if report.ok and report.manifest_exists else "warning"
    if not report.writable:
        status = "critical"
    repair_actions: list[str] = []
    if not report.manifest_exists:
        repair_actions.append("review_storage_config")
    return MemoryCommandDoctorCheck(
        id="context_bundle_manifest",
        category="storage",
        label="Context bundle manifest",
        status=status,
        evidence=(
            f"Bundle manifest {'present' if report.manifest_exists else 'missing'}; "
            f"writable={report.writable}; pending_actions={len(report.actions)}."
        ),
        impact="Unified context export/import and scene health depend on a valid bundle manifest.",
        next_action="No action required."
        if report.manifest_exists and report.writable
        else "Run context bundle migration from Settings or Doctor.",
        repair_actions=repair_actions,
    )


def probe_capacity_theater(
    *,
    total_active_chars: int = 0,
    working_memory_count: int = 0,
    unpinned_count: int = 0,
    budget_limit: int = 6000,
) -> MemoryCommandDoctorCheck:
    """Evaluate whether the active memory stack suffers from capacity theater or causal blindness."""
    is_overflow = total_active_chars > budget_limit
    is_bloated = working_memory_count > 30 or unpinned_count > 40
    has_risk = is_overflow or is_bloated

    status: DiagnosticStatus = "warning" if has_risk else "ready"
    repair_actions: list[str] = ["restore_disciplined_defaults"] if has_risk else []

    evidence = (
        f"Active memory load: {total_active_chars}/{budget_limit} chars, "
        f"{working_memory_count} working memories, {unpinned_count} unpinned entries."
        if has_risk
        else f"Disciplined memory load within budget: {total_active_chars}/{budget_limit} chars."
    )
    impact = (
        "Memory stack bloating causes causal blindness, attention dilution, and higher token billing."
        if has_risk
        else "Disciplined memory footprint preserves prompt prefix caching and sharp attention focus."
    )
    next_action = (
        "Restore disciplined defaults to archive unpinned working memories safely." if has_risk else "No action required."
    )

    return MemoryCommandDoctorCheck(
        id="capacity_theater",
        category="governance",
        label="Capacity theater & memory discipline",
        status=status,
        evidence=evidence,
        impact=impact,
        next_action=next_action,
        can_auto_fix=has_risk,
        repair_actions=repair_actions,
    )
