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


def probe_relational_store(runtime: MemoryCommandRuntimeStatus) -> MemoryCommandDoctorCheck:
    return MemoryCommandDoctorCheck(
        id="relational_store",
        category="storage",
        label="Relational store",
        status="ready" if runtime.relational_status == "available" else "critical",
        evidence=f"Relational memory store is {runtime.relational_status}.",
        impact="Profile, procedural, governance, and audit data depend on the relational store.",
        next_action="No action required."
        if runtime.relational_status == "available"
        else "Review the SQLite database path and permissions.",
        repair_actions=[] if runtime.relational_status == "available" else ["review_storage_config"],
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
    return MemoryCommandDoctorCheck(
        id="vector_index",
        category="index",
        label="Vector index",
        status="ready" if runtime.vector_status == "available" else "missing",
        evidence=f"Vector recall backend is {runtime.vector_status}.",
        impact="Semantic and episodic memories need vector search for high-recall cross-session retrieval.",
        next_action="No action required."
        if runtime.vector_status == "available"
        else "Enable vector storage and configure embeddings.",
        repair_actions=[] if runtime.vector_status == "available" else ["enable_vector_store", "configure_embedding"],
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
        next_action="No action required." if runtime.event_ledger_status == "available" else "Review local database configuration.",
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
            f"Supported clients: {', '.join(runtime.supported_clients)}; "
            f"control plane status: {runtime.control_plane_status}."
        ),
        impact="Business memory content stays inside the local or per-user sandbox boundary.",
        next_action="No action required.",
        repair_actions=[],
    )


def probe_context_bundle_manifest(runtime: MemoryCommandRuntimeStatus) -> MemoryCommandDoctorCheck:
    from myrm_agent_harness.toolkits.context import run_migration_dry_run

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
