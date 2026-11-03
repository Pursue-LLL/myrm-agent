"""Executable memory diagnostics service.

[INPUT]
app.schemas.memory.command_center::MemoryCommandRuntimeStatus (POS: Deployment and storage status visible to the local memory UI)
app.services.memory.diagnostics.diagnostic.diagnostic_live_probes (POS: 单用户记忆诊断的运行期探针)
app.services.memory.diagnostics.diagnostic.diagnostic_migration_integrity (POS: 单用户记忆迁移完整性检查)
app.services.memory.ledger.operation_ledger::MemoryOperationLedgerService (POS: 记忆操作账本服务)

[OUTPUT]
MemoryDiagnosticsService: builds Memory Doctor checks, executes probe-level diagnostics including migration integrity, and returns SLO evidence.

[POS]
单用户记忆诊断服务。验证本地/沙箱内记忆运行依赖、迁移账本完整性、召回基准和质量治理，不读取或上报业务记忆内容到控制平面。
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from time import perf_counter
from uuid import uuid4

from myrm_agent_harness.toolkits.memory import MemoryManager, MemoryOperationKind, MemoryOperationStatus, MemoryType
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.memory.command_center import (
    MemoryCommandDiagnosticProbeResult,
    MemoryCommandDiagnosticRun,
    MemoryCommandDoctorCheck,
    MemoryCommandRuntimeStatus,
)
from app.services.memory.diagnostics.diagnostic.diagnostic_live_probes import (
    run_embedding_live_probe,
    run_retrieval_pipeline_probe,
    run_sparse_cjk_recall_probe,
)
from app.services.memory.diagnostics.diagnostic.diagnostic_migration_integrity import (
    inspect_migration_integrity,
    run_migration_integrity_probe,
)
from app.services.memory.diagnostics.diagnostic.diagnostic_probe_results import (
    DiagnosticStatus,
    doctor_check_to_probe,
    operation_status,
    rollup_status,
    run_summary,
)
from app.services.memory.diagnostics.diagnostic.diagnostic_quality_governance import run_memory_quality_probe
from app.services.memory.diagnostics.diagnostic.diagnostic_recall_benchmark import run_golden_recall_benchmark
from app.services.memory.diagnostics.diagnostic.diagnostic_repair_plans import with_check_repair_plans, with_probe_repair_plans
from app.services.memory.diagnostics.diagnostic.diagnostic_slo import build_diagnostic_slo
from app.services.memory.diagnostics.diagnostic.diagnostic_static_checks import (
    probe_capacity_theater,
    probe_context_bundle_manifest,
    probe_deployment_boundary,
    probe_embedding_provider,
    probe_event_ledger_snapshot,
    probe_health_snapshot,
    probe_knowledge_graph,
    probe_memory_base_path,
    probe_relational_store,
    probe_vector_index,
)
from app.services.memory.ledger.operation_ledger import JsonObject, MemoryOperationLedgerService

_CAPACITY_SAMPLE_TYPES = (MemoryType.PROFILE, MemoryType.TASK_DIGEST, MemoryType.CONVERSATION, MemoryType.SEMANTIC)
_CAPACITY_SAMPLE_LIMIT = 20


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

        capacity_check = await self._check_capacity()
        relational_check = await self._check_relational_store(runtime)
        checks = [
            relational_check,
            probe_memory_base_path(runtime),
            probe_vector_index(runtime),
            probe_knowledge_graph(runtime),
            probe_embedding_provider(runtime),
            probe_event_ledger_snapshot(runtime),
            probe_health_snapshot(health_cache_status),
            capacity_check,
            probe_context_bundle_manifest(runtime),
            probe_deployment_boundary(runtime),
            await inspect_migration_integrity(self._db),
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

        capacity_check = await self._check_capacity()
        relational_check = await self._check_relational_store(runtime)
        probes = [
            await self._run_probe(lambda: relational_check),
            await self._run_probe(lambda: probe_memory_base_path(runtime)),
            await self._run_probe(lambda: probe_vector_index(runtime)),
            await self._run_probe(lambda: probe_knowledge_graph(runtime)),
            await self._run_probe(lambda: probe_embedding_provider(runtime)),
            await self._run_probe(lambda: capacity_check),
            await run_embedding_live_probe(),
            await run_retrieval_pipeline_probe(self._memory_manager),
            await run_sparse_cjk_recall_probe(self._memory_manager),
            await run_golden_recall_benchmark(self._memory_manager, run_id=run_id),
            await run_memory_quality_probe(self._memory_manager),
            await self._run_event_ledger_probe(run_id),
            await run_migration_integrity_probe(self._db),
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

    async def _check_capacity(self) -> MemoryCommandDoctorCheck:
        """Sample the active memory load; a failed read keeps the counts gathered so far."""
        total_chars = 0
        session_memory_count = 0
        unpinned_count = 0
        if self._memory_manager is not None:
            try:
                for mtype in _CAPACITY_SAMPLE_TYPES:
                    items = await self._memory_manager.list_memories(mtype, limit=_CAPACITY_SAMPLE_LIMIT)
                    for item in items:
                        content_str = str(getattr(item, "content", "") or "")
                        total_chars += len(content_str)
                        if mtype in (MemoryType.TASK_DIGEST, MemoryType.CONVERSATION):
                            session_memory_count += 1
                        if not getattr(item, "pinned", False):
                            unpinned_count += 1
            except Exception:
                pass
        return probe_capacity_theater(
            total_active_chars=total_chars,
            session_memory_count=session_memory_count,
            unpinned_count=unpinned_count,
        )

    async def _check_relational_store(self, runtime: MemoryCommandRuntimeStatus) -> MemoryCommandDoctorCheck:
        """Run the relational store integrity check when the manager exposes one."""
        integrity_ok = True
        integrity_detail = "ok"
        if self._memory_manager is not None and hasattr(self._memory_manager, "_relational"):
            try:
                rel_store = self._memory_manager._relational
                if rel_store is not None and hasattr(rel_store, "check_integrity"):
                    integrity_ok, integrity_detail = await rel_store.check_integrity()
            except Exception as e:
                integrity_ok = False
                integrity_detail = str(e)
        return probe_relational_store(runtime, integrity_ok=integrity_ok, integrity_detail=integrity_detail)

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
            impact = (
                "Memory replay, diagnostic history, and governance audit trails cannot be trusted until ledger writes recover."
            )
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

    async def _record_run_event(self, run: MemoryCommandDiagnosticRun) -> tuple[bool, str | None]:
        metadata: JsonObject = {
            "diagnostic_run_id": run.id,
            "diagnostic_status": run.status,
            "probe_count": run.probe_count,
            "failed_count": run.failed_count,
            "duration_ms": run.duration_ms,
        }
        metadata.update(self._flatten_benchmark_metrics(run))
        try:
            await self._ledger.record_event(
                kind=MemoryOperationKind.HEALTH_CHECK,
                status=operation_status(run.status),
                summary=f"Memory diagnostics completed with {run.failed_count} failed probes.",
                source="memory_diagnostics",
                target_kind="health",
                target_id="diagnostic_run",
                correlation_id=run.id,
                metadata=metadata,
                commit=True,
            )
            return True, None
        except Exception as exc:
            await self._db.rollback()
            return False, f"Diagnostic audit event failed to persist: {type(exc).__name__}"

    def _flatten_benchmark_metrics(self, run: MemoryCommandDiagnosticRun) -> JsonObject:
        """Flatten golden recall benchmark metrics into ledger metadata.

        Scalar metrics are stored directly; per-category pass/total detail is
        stored as a nested object so trend history can localize regressions to a
        specific memory category. The JSON `metadata` column supports nested
        values; SSE coercion keeps only scalars, and the history projection reads
        the raw column.
        """

        probe = next((p for p in run.probes if p.id == "golden_recall_benchmark" and p.benchmark_summary), None)
        if probe is None or probe.benchmark_summary is None:
            return {}
        summary = probe.benchmark_summary
        metrics: JsonObject = {
            "benchmark_case_count": summary.case_count,
            "benchmark_passed_count": summary.passed_count,
            "benchmark_recall_at_k": summary.recall_at_k,
            "benchmark_ndcg_at_k": summary.ndcg_at_k,
            "benchmark_mrr_score": summary.mrr_score,
            "benchmark_precision_at_k": summary.precision_at_k,
            "benchmark_latency_p50_ms": summary.latency_p50_ms,
            "benchmark_latency_p95_ms": summary.latency_p95_ms,
            "benchmark_latency_p99_ms": summary.latency_p99_ms,
            "benchmark_top_k": summary.top_k,
        }
        if summary.categories:
            metrics["benchmark_categories"] = dict(summary.categories)
        embedding_model = self._resolve_embedding_model()
        if embedding_model:
            metrics["benchmark_embedding_model"] = embedding_model
        return metrics

    def _resolve_embedding_model(self) -> str | None:
        """Resolve the active embedding model for baseline-shift annotation in trends."""
        if self._memory_manager is None:
            return None
        return self._memory_manager.config.embedding_model


type ProbeFactory = Callable[[], MemoryCommandDoctorCheck]
