"""Executable memory diagnostics service.

[INPUT]
app.schemas.memory.command_center::MemoryCommandRuntimeStatus (POS: Deployment and storage status visible to the local memory UI)
app.services.memory.operation_ledger::MemoryOperationLedgerService (POS: 记忆操作账本服务)

[OUTPUT]
MemoryDiagnosticsService: builds Memory Doctor checks, executes probe-level diagnostics including migration integrity, and returns SLO evidence.

[POS]
单用户记忆诊断服务。验证本地/沙箱内记忆运行依赖、迁移账本完整性、召回基准和质量治理，不读取或上报业务记忆内容到控制平面。
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from datetime import UTC, datetime
from time import perf_counter
from uuid import uuid4

from myrm_agent_harness.toolkits.memory import MemoryManager, MemoryOperationKind, MemoryOperationStatus, MemoryType
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.memory.command_center import (
    MemoryCommandDiagnosticProbeResult,
    MemoryCommandDiagnosticRun,
    MemoryCommandDoctorCheck,
    MemoryCommandRuntimeStatus,
)
from app.services.memory.diagnostic_probe_results import (
    critical_probe,
    doctor_check_to_probe,
    missing_probe,
    operation_status,
    rollup_status,
    run_summary,
)
from app.services.memory.diagnostic_quality_governance import run_memory_quality_probe
from app.services.memory.diagnostic_recall_benchmark import run_golden_recall_benchmark
from app.services.memory.diagnostic_repair_plans import with_check_repair_plans, with_probe_repair_plans
from app.services.memory.diagnostic_slo import build_diagnostic_slo
from app.services.memory.diagnostic_static_checks import (
    probe_deployment_boundary,
    probe_embedding_provider,
    probe_event_ledger_snapshot,
    probe_health_snapshot,
    probe_knowledge_graph,
    probe_memory_base_path,
    probe_relational_store,
    probe_vector_index,
)
from app.services.memory.operation_ledger import MemoryOperationLedgerService
from app.services.memory.shared_context_health import check_shared_context_memory_health

DiagnosticStatus = str


class MemoryDiagnosticsService:
    """Builds visible doctor checks and runs executable memory diagnostics."""

    def __init__(
        self,
        db: AsyncSession,
        memory_manager: MemoryManager | None = None,
        ledger: MemoryOperationLedgerService | None = None,
    ) -> None:
        self._db = db
        self._memory_manager = memory_manager
        self._ledger = ledger or MemoryOperationLedgerService(db)

    async def build_doctor_checks(
        self,
        *,
        health_cache_status: str,
        runtime: MemoryCommandRuntimeStatus,
    ) -> list[MemoryCommandDoctorCheck]:
        """Return snapshot doctor checks without mutating storage."""

        checks = [
            probe_relational_store(runtime),
            probe_memory_base_path(runtime),
            probe_vector_index(runtime),
            probe_knowledge_graph(runtime),
            probe_embedding_provider(runtime),
            probe_event_ledger_snapshot(runtime),
            probe_health_snapshot(health_cache_status),
            probe_deployment_boundary(runtime),
            await self._inspect_migration_integrity(),
        ]
        return [with_check_repair_plans(check) for check in checks]

    async def run_diagnostics(
        self,
        *,
        health_cache_status: str,
        runtime: MemoryCommandRuntimeStatus,
    ) -> MemoryCommandDiagnosticRun:
        """Execute a probe pack and persist a content-free diagnostic audit event."""

        run_id = f"memory-diagnostic:{uuid4().hex}"
        started_at = datetime.now(UTC)
        started_timer = perf_counter()
        probes = [
            await self._run_probe(lambda: probe_relational_store(runtime)),
            await self._run_probe(lambda: probe_memory_base_path(runtime)),
            await self._run_probe(lambda: probe_vector_index(runtime)),
            await self._run_probe(lambda: probe_knowledge_graph(runtime)),
            await self._run_probe(lambda: probe_embedding_provider(runtime)),
            await self._run_embedding_live_probe(),
            await self._run_retrieval_pipeline_probe(),
            await self._run_sparse_cjk_recall_probe(),
            await run_golden_recall_benchmark(self._memory_manager, run_id=run_id),
            await run_memory_quality_probe(self._memory_manager),
            await self._run_event_ledger_probe(run_id),
            await self._run_migration_integrity_probe(),
            await self._run_probe(lambda: probe_health_snapshot(health_cache_status)),
            await self._run_probe(lambda: probe_deployment_boundary(runtime)),
        ]
        probes = [with_probe_repair_plans(probe) for probe in probes]
        completed_at = datetime.now(UTC)
        duration_ms = round((perf_counter() - started_timer) * 1000, 2)
        failed_count = sum(1 for probe in probes if probe.status != "ready")
        run_status = rollup_status([probe.status for probe in probes])
        run = MemoryCommandDiagnosticRun(
            id=run_id,
            status=run_status,
            summary=run_summary(run_status, failed_count, len(probes)),
            started_at=started_at,
            completed_at=completed_at,
            duration_ms=duration_ms,
            probe_count=len(probes),
            failed_count=failed_count,
            probes=probes,
        )
        audit_recorded, audit_error = await self._record_run_event(run)
        slo = await build_diagnostic_slo(self._ledger)
        return run.model_copy(update={"audit_recorded": audit_recorded, "audit_error": audit_error, "slo": slo})

    async def _run_probe(self, factory: "ProbeFactory") -> MemoryCommandDiagnosticProbeResult:
        started = perf_counter()
        check = factory()
        return doctor_check_to_probe(check, duration_ms=round((perf_counter() - started) * 1000, 2))

    async def _run_event_ledger_probe(self, run_id: str) -> MemoryCommandDiagnosticProbeResult:
        started = perf_counter()
        try:
            await self._ledger.record_event(
                kind=MemoryOperationKind.HEALTH_CHECK,
                status=MemoryOperationStatus.SUCCESS,
                summary="Memory diagnostics event ledger roundtrip succeeded.",
                source="memory_diagnostics",
                target_kind="health",
                target_id="event_ledger",
                correlation_id=run_id,
                metadata={"diagnostic_run_id": run_id, "diagnostic_probe": "event_ledger"},
                commit=True,
            )
            status: DiagnosticStatus = "ready"
            evidence = "Event ledger accepted and committed a content-free diagnostic event."
            repair_actions: list[str] = []
            impact = "Trace, replay, and governance audit evidence can be persisted for later inspection."
            next_action = "No action required."
            safe_to_retry = True
        except Exception as exc:
            await self._db.rollback()
            status = "critical"
            evidence = f"Event ledger roundtrip failed: {exc}"
            repair_actions = ["review_storage_config"]
            impact = "Memory replay, diagnostic history, and governance audit trails cannot be trusted until ledger writes recover."
            next_action = "Review the local database and storage configuration, then rerun diagnostics."
            safe_to_retry = True
        return MemoryCommandDiagnosticProbeResult(
            id="event_ledger",
            category="ledger",
            label="Event ledger",
            status=status,
            evidence=evidence,
            impact=impact,
            next_action=next_action,
            safe_to_retry=safe_to_retry,
            duration_ms=round((perf_counter() - started) * 1000, 2),
            repair_actions=repair_actions,
        )

    async def _run_embedding_live_probe(self) -> MemoryCommandDiagnosticProbeResult:
        started = perf_counter()
        result = await check_shared_context_memory_health(probe=True)
        if result.ready:
            status: DiagnosticStatus = "ready"
            evidence = f"Embedding live probe succeeded for model {result.model}; dimension={result.vector_dimension}."
            repair_actions: list[str] = []
        elif result.status == "not_configured":
            status = "critical"
            evidence = f"Embedding live probe was not configured: {result.reason}."
            repair_actions = ["configure_embedding"]
        else:
            status = "critical"
            evidence = f"Embedding live probe failed: {result.reason}."
            repair_actions = ["configure_embedding", "run_diagnostics"]
        return MemoryCommandDiagnosticProbeResult(
            id="embedding_live",
            category="embedding",
            label="Embedding live probe",
            status=status,
            evidence=evidence,
            impact="Semantic and episodic memories cannot be reliably indexed or recalled if live embeddings fail.",
            next_action="Configure a working embedding provider and rerun diagnostics."
            if status != "ready"
            else "No action required.",
            safe_to_retry=result.retryable,
            duration_ms=round((perf_counter() - started) * 1000, 2),
            repair_actions=repair_actions,
        )

    async def _run_retrieval_pipeline_probe(self) -> MemoryCommandDiagnosticProbeResult:
        started = perf_counter()
        manager = self._memory_manager
        if manager is None:
            return missing_probe(
                probe_id="retrieval_pipeline",
                category="index",
                label="Retrieval pipeline",
                started=started,
                evidence="Memory manager dependency was not available to diagnostics.",
                impact="Search, RRF fusion, trace capture, and graph enrichment cannot be proven from this run.",
                next_action="Open the memory command center through the normal GUI runtime and rerun diagnostics.",
            )
        if not manager.get_enabled_types():
            return missing_probe(
                probe_id="retrieval_pipeline",
                category="index",
                label="Retrieval pipeline",
                started=started,
                evidence="No enabled memory types are available for retrieval.",
                impact="The agent has no searchable persistent memory backends in this runtime.",
                next_action="Enable relational or vector memory storage, then rerun diagnostics.",
            )
        try:
            results = await manager.search("memory reliability retrieval probe 记忆诊断", limit=1)
            trace = manager.last_retrieval_trace
        except Exception as exc:
            return critical_probe(
                probe_id="retrieval_pipeline",
                category="index",
                label="Retrieval pipeline",
                started=started,
                evidence=f"Retrieval pipeline probe failed: {exc}",
                impact="Cross-session recall and memory injection may fail during normal agent work.",
                next_action="Review embedding, vector, and relational storage configuration, then rerun diagnostics.",
                repair_actions=["review_storage_config", "configure_embedding"],
            )
        trace_steps = len(trace.steps) if trace is not None else 0
        status: DiagnosticStatus = "ready" if trace_steps else "warning"
        return MemoryCommandDiagnosticProbeResult(
            id="retrieval_pipeline",
            category="index",
            label="Retrieval pipeline",
            status=status,
            evidence=f"Search completed with {len(results)} result(s); retrieval trace steps={trace_steps}.",
            impact="The recall path can execute without exposing retrieved memory content in diagnostic evidence.",
            next_action="No action required." if status == "ready" else "Inspect retrieval trace capture and rerun diagnostics.",
            safe_to_retry=True,
            duration_ms=round((perf_counter() - started) * 1000, 2),
            repair_actions=[] if status == "ready" else ["run_diagnostics"],
        )

    async def _run_sparse_cjk_recall_probe(self) -> MemoryCommandDiagnosticProbeResult:
        started = perf_counter()
        manager = self._memory_manager
        if manager is None or not manager.has_vector:
            return missing_probe(
                probe_id="sparse_cjk_recall",
                category="index",
                label="Sparse CJK recall",
                started=started,
                evidence="Vector-backed memory search is unavailable, so BM25/RRF sparse recall was not executed.",
                impact="Exact keyword recall and CJK query coverage cannot be proven in this runtime.",
                next_action="Enable vector-backed memory search and rerun diagnostics.",
            )
        try:
            await manager.search(
                "记忆诊断 precise keyword BM25 CJK",
                memory_types=[MemoryType.SEMANTIC, MemoryType.EPISODIC],
                limit=1,
                use_rrf=True,
            )
        except Exception as exc:
            return critical_probe(
                probe_id="sparse_cjk_recall",
                category="index",
                label="Sparse CJK recall",
                started=started,
                evidence=f"Sparse CJK recall probe failed: {exc}",
                impact="Hybrid keyword + semantic recall may miss exact file names, identifiers, and Chinese/Japanese/Korean queries.",
                next_action="Review vector store and BM25 dependencies, then rerun diagnostics.",
                repair_actions=["enable_vector_store", "run_diagnostics"],
            )
        config = manager.config
        return MemoryCommandDiagnosticProbeResult(
            id="sparse_cjk_recall",
            category="index",
            label="Sparse CJK recall",
            status="ready",
            evidence=f"Hybrid retrieval accepted a CJK keyword query with RRF enabled; bm25_top_k={config.bm25_top_k}, max_corpus={config.bm25_max_corpus_size}.",
            impact="Exact keyword recall is available as a complement to semantic vector search.",
            next_action="No action required.",
            safe_to_retry=True,
            duration_ms=round((perf_counter() - started) * 1000, 2),
            repair_actions=[],
        )

    async def _run_migration_integrity_probe(self) -> MemoryCommandDiagnosticProbeResult:
        started = perf_counter()
        check = await self._inspect_migration_integrity()
        return doctor_check_to_probe(check, duration_ms=round((perf_counter() - started) * 1000, 2))

    async def _inspect_migration_integrity(self) -> MemoryCommandDoctorCheck:
        try:
            from app.database.migrations import MIGRATION_STATEMENTS

            expected = {
                index: hashlib.sha256(sql.encode("utf-8")).hexdigest()
                for index, sql in enumerate(MIGRATION_STATEMENTS)
            }
            result = await self._db.execute(text("SELECT version, checksum FROM _schema_migrations"))
            applied: dict[int, str] = {int(row[0]): str(row[1]) for row in result.fetchall()}
        except Exception as exc:
            return MemoryCommandDoctorCheck(
                id="migration_integrity",
                category="migration",
                label="Migration integrity",
                status="critical",
                evidence=f"Migration state inspection failed: {type(exc).__name__}.",
                impact="The local schema migration ledger cannot be trusted until the database state table is readable.",
                next_action="Review the SQLite database state and rerun diagnostics.",
                safe_to_retry=True,
                repair_actions=["review_storage_config", "run_diagnostics"],
            )

        drifted = [
            version
            for version, checksum in applied.items()
            if version in expected and not checksum.startswith("baselined:") and checksum != expected[version]
        ]
        pending = [version for version in expected if version not in applied]
        unknown = [version for version in applied if version not in expected]
        if drifted:
            status: DiagnosticStatus = "critical"
            next_action = "Do not modify historical migrations; create a forward repair migration or rebuild an isolated sandbox."
            repair_actions = ["review_storage_config"]
        elif pending or unknown:
            status = "warning"
            next_action = "Restart through the normal app lifecycle so pending migrations can apply, then rerun diagnostics."
            repair_actions = ["run_diagnostics"]
        else:
            status = "ready"
            next_action = "No action required."
            repair_actions = []
        evidence = (
            f"Migration ledger checked {len(applied)} applied version(s); "
            f"drifted={len(drifted)}, pending={len(pending)}, unknown={len(unknown)}."
        )
        return MemoryCommandDoctorCheck(
            id="migration_integrity",
            category="migration",
            label="Migration integrity",
            status=status,
            evidence=evidence,
            impact="Schema integrity protects startup, rollback, import review storage, and command-center audit durability.",
            next_action=next_action,
            safe_to_retry=True,
            repair_actions=repair_actions,
        )

    async def _record_run_event(self, run: MemoryCommandDiagnosticRun) -> tuple[bool, str | None]:
        try:
            await self._ledger.record_event(
                kind=MemoryOperationKind.HEALTH_CHECK,
                status=operation_status(run.status),
                summary=f"Memory diagnostics completed with {run.failed_count} failed probes.",
                source="memory_diagnostics",
                target_kind="health",
                target_id="diagnostic_run",
                correlation_id=run.id,
                metadata={
                    "diagnostic_run_id": run.id,
                    "diagnostic_status": run.status,
                    "probe_count": run.probe_count,
                    "failed_count": run.failed_count,
                    "duration_ms": run.duration_ms,
                },
                commit=True,
            )
            return True, None
        except Exception as exc:
            await self._db.rollback()
            return False, f"Diagnostic audit event failed to persist: {type(exc).__name__}"

type ProbeFactory = Callable[[], MemoryCommandDoctorCheck]
