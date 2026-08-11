"""Unit tests for diagnostic history persistence and retrieval.

Covers `MemoryDiagnosticsService._flatten_benchmark_metrics`, ledger diagnostic
event filtering, and the command-center history item projection.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from app.api.memory.operations.command_center import _diagnostic_history_item
from app.database.models.memory import MemoryOperationEventModel
from app.schemas.memory.command_center import (
    MemoryCommandBenchmarkSummary,
    MemoryCommandDiagnosticProbeResult,
    MemoryCommandDiagnosticRun,
)
from app.services.memory.diagnostics import MemoryDiagnosticsService


def _make_diagnostic_run(*, benchmark: bool) -> MemoryCommandDiagnosticRun:
    probes: list[MemoryCommandDiagnosticProbeResult] = []
    if benchmark:
        probes.append(
            MemoryCommandDiagnosticProbeResult(
                id="golden_recall_benchmark",
                category="index",
                label="Golden recall benchmark",
                status="ready",
                evidence="ok",
                benchmark_summary=MemoryCommandBenchmarkSummary(
                    case_count=16,
                    passed_count=15,
                    recall_at_k=0.94,
                    ndcg_at_k=0.88,
                    mrr_score=0.91,
                    precision_at_k=0.12,
                    latency_p50_ms=10.5,
                    latency_p95_ms=24.0,
                    top_k=5,
                    categories={"arch": "2/2"},
                ),
            )
        )
    return MemoryCommandDiagnosticRun(
        id="run-1",
        status="ready",
        summary="ok",
        started_at=datetime.now(UTC),
        completed_at=datetime.now(UTC),
        duration_ms=1200.0,
        probe_count=len(probes),
        failed_count=0,
        probes=probes,
    )


class TestFlattenBenchmarkMetrics:
    def test_flattens_scalar_metrics_when_benchmark_present(self) -> None:
        service = MemoryDiagnosticsService(AsyncMock(), None)
        metrics = service._flatten_benchmark_metrics(_make_diagnostic_run(benchmark=True))

        assert metrics["benchmark_case_count"] == 16
        assert metrics["benchmark_passed_count"] == 15
        assert metrics["benchmark_recall_at_k"] == 0.94
        assert metrics["benchmark_ndcg_at_k"] == 0.88
        assert metrics["benchmark_mrr_score"] == 0.91
        assert metrics["benchmark_precision_at_k"] == 0.12
        assert metrics["benchmark_latency_p50_ms"] == 10.5
        assert metrics["benchmark_latency_p95_ms"] == 24.0
        assert metrics["benchmark_top_k"] == 5
        # per-category detail must persist for trend-localized regression analysis
        assert metrics["benchmark_categories"] == {"arch": "2/2"}

    def test_empty_when_no_benchmark_probe(self) -> None:
        service = MemoryDiagnosticsService(AsyncMock(), None)
        metrics = service._flatten_benchmark_metrics(_make_diagnostic_run(benchmark=False))
        assert metrics == {}

    def test_empty_when_benchmark_probe_without_summary(self) -> None:
        probes = [
            MemoryCommandDiagnosticProbeResult(
                id="golden_recall_benchmark",
                category="index",
                label="Golden recall benchmark",
                status="ready",
                evidence="no summary",
            )
        ]
        run = MemoryCommandDiagnosticRun(
            id="run-2",
            status="ready",
            summary="ok",
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
            duration_ms=100.0,
            probe_count=1,
            failed_count=0,
            probes=probes,
        )
        service = MemoryDiagnosticsService(AsyncMock(), None)
        assert service._flatten_benchmark_metrics(run) == {}

    def test_resolve_embedding_model_none_when_manager_missing(self) -> None:
        service = MemoryDiagnosticsService(AsyncMock(), None)
        assert service._resolve_embedding_model() is None

    def test_resolve_embedding_model_from_manager_config(self) -> None:
        manager = MagicMock()
        manager.config.embedding_model = "text-embedding-3-small"
        service = MemoryDiagnosticsService(AsyncMock(), manager)
        assert service._resolve_embedding_model() == "text-embedding-3-small"

    def test_embedding_model_included_in_flattened_metrics(self) -> None:
        manager = MagicMock()
        manager.config.embedding_model = "text-embedding-3-small"
        service = MemoryDiagnosticsService(AsyncMock(), manager)
        metrics = service._flatten_benchmark_metrics(_make_diagnostic_run(benchmark=True))
        assert metrics["benchmark_embedding_model"] == "text-embedding-3-small"

    def test_empty_embedding_model_omitted_from_flattened_metrics(self) -> None:
        manager = MagicMock()
        manager.config.embedding_model = ""
        service = MemoryDiagnosticsService(AsyncMock(), manager)
        metrics = service._flatten_benchmark_metrics(_make_diagnostic_run(benchmark=True))
        assert "benchmark_embedding_model" not in metrics


class TestRecordRunEventMetadata:
    async def test_metadata_merged_into_record_event_call(self) -> None:
        service = MemoryDiagnosticsService(AsyncMock(), None)
        run = _make_diagnostic_run(benchmark=True)
        ledger = MagicMock()
        ledger.record_event = AsyncMock(return_value=SimpleNamespace())
        service._ledger = ledger

        recorded, error = await await_ready(service, run)
        assert recorded is True
        assert error is None
        call_kwargs = ledger.record_event.await_args.kwargs
        assert call_kwargs["metadata"]["benchmark_recall_at_k"] == 0.94
        assert call_kwargs["metadata"]["diagnostic_run_id"] == "run-1"
        # per-category detail must reach ledger metadata for history reconstruction
        assert call_kwargs["metadata"]["benchmark_categories"] == {"arch": "2/2"}

    async def test_record_event_failure_returns_error(self) -> None:
        service = MemoryDiagnosticsService(AsyncMock(), None)
        run = _make_diagnostic_run(benchmark=False)
        ledger = MagicMock()
        ledger.record_event = AsyncMock(side_effect=RuntimeError("ledger down"))
        service._ledger = ledger

        recorded, error = await await_ready(service, run)
        assert recorded is False
        assert error is not None
        assert "RuntimeError" in error


async def await_ready(service: MemoryDiagnosticsService, run: MemoryCommandDiagnosticRun) -> tuple[bool, str | None]:
    return await service._record_run_event(run)


class TestDiagnosticHistoryItemProjection:
    def test_projects_benchmark_from_flat_metadata(self) -> None:
        row = MemoryOperationEventModel(
            id="evt-1",
            kind="health_check",
            status="success",
            occurred_at=datetime(2026, 8, 1, 12, 0, tzinfo=UTC),
            source="memory_diagnostics",
            target_kind="health",
            target_id="diagnostic_run",
            metadata_json={
                "diagnostic_run_id": "run-9",
                "diagnostic_status": "ready",
                "probe_count": 14,
                "failed_count": 1,
                "duration_ms": 1100.0,
                "benchmark_case_count": 16,
                "benchmark_passed_count": 15,
                "benchmark_recall_at_k": 0.94,
                "benchmark_ndcg_at_k": 0.88,
                "benchmark_mrr_score": 0.91,
                "benchmark_precision_at_k": 0.12,
                "benchmark_latency_p50_ms": 10.5,
                "benchmark_latency_p95_ms": 24.0,
                "benchmark_top_k": 5,
                "benchmark_categories": {"arch": "2/2", "workflow": "1/2"},
                "benchmark_embedding_model": "text-embedding-3-small",
            },
        )

        item = _diagnostic_history_item(row)
        assert item.run_id == "run-9"
        assert item.status == "ready"
        assert item.failed_count == 1
        assert item.benchmark is not None
        assert item.benchmark.recall_at_k == 0.94
        assert item.benchmark.ndcg_at_k == 0.88
        assert item.benchmark.mrr_score == 0.91
        assert item.benchmark.case_count == 16
        assert item.benchmark.top_k == 5
        # per-category detail is restored from ledger metadata for trend regression analysis
        assert item.benchmark.categories == {"arch": "2/2", "workflow": "1/2"}
        assert item.embedding_model == "text-embedding-3-small"
        assert item.occurred_at.tzinfo is not None

    def test_projects_naive_occurred_at_as_utc(self) -> None:
        row = MemoryOperationEventModel(
            id="evt-5",
            kind="health_check",
            status="ready",
            occurred_at=datetime(2026, 8, 1, 12, 0),
            source="memory_diagnostics",
            target_kind="health",
            target_id="diagnostic_run",
            metadata_json={"diagnostic_run_id": "run-11", "benchmark_recall_at_k": 0.9},
        )

        item = _diagnostic_history_item(row)
        assert item.occurred_at.tzinfo is not None
        assert item.occurred_at.utcoffset() == timedelta(0)

    def test_drops_empty_embedding_model(self) -> None:
        row = MemoryOperationEventModel(
            id="evt-6",
            kind="health_check",
            status="ready",
            occurred_at=datetime(2026, 8, 1, 12, 0, tzinfo=UTC),
            source="memory_diagnostics",
            target_kind="health",
            target_id="diagnostic_run",
            metadata_json={
                "diagnostic_run_id": "run-12",
                "benchmark_recall_at_k": 0.9,
                "benchmark_embedding_model": "",
            },
        )

        item = _diagnostic_history_item(row)
        assert item.embedding_model is None

    def test_projects_without_benchmark_metadata(self) -> None:
        row = MemoryOperationEventModel(
            id="evt-2",
            kind="health_check",
            status="warning",
            occurred_at=datetime(2026, 7, 30, 9, 0, tzinfo=UTC),
            source="memory_diagnostics",
            target_kind="health",
            target_id="diagnostic_run",
            metadata_json={
                "diagnostic_run_id": "run-8",
                "diagnostic_status": "warning",
                "probe_count": 14,
                "failed_count": 2,
                "duration_ms": 900.0,
            },
        )

        item = _diagnostic_history_item(row)
        assert item.benchmark is None
        assert item.embedding_model is None
        assert item.status == "warning"

    def test_falls_back_to_event_status_and_id(self) -> None:
        row = MemoryOperationEventModel(
            id="evt-3",
            kind="health_check",
            status="critical",
            occurred_at=datetime(2026, 7, 29, 9, 0, tzinfo=UTC),
            source="memory_diagnostics",
            target_kind="health",
            target_id="diagnostic_run",
            metadata_json=None,
        )

        item = _diagnostic_history_item(row)
        assert item.run_id == "evt-3"
        assert item.status == "critical"
        assert item.benchmark is None


class TestListDiagnosticEvents:
    async def test_filters_diagnostic_run_audit_events(self) -> None:
        from app.services.memory.operation_ledger import MemoryOperationLedgerService

        db = AsyncMock()
        result = MagicMock()
        row = MemoryOperationEventModel(
            id="evt-4",
            kind="health_check",
            status="ready",
            occurred_at=datetime(2026, 8, 2, 8, 0, tzinfo=UTC),
            source="memory_diagnostics",
            target_kind="health",
            target_id="diagnostic_run",
            metadata_json={"diagnostic_run_id": "run-10", "benchmark_recall_at_k": 0.9},
        )
        result.scalars.return_value.all.return_value = [row]
        db.execute.return_value = result

        service = MemoryOperationLedgerService(db)
        events = await service.list_diagnostic_events(limit=10, offset=5)

        assert events == [row]
        # query must target diagnostic run audit rows
        query = db.execute.await_args.args[0]
        compiled = str(query.compile(compile_kwargs={"literal_binds": True}))
        assert "memory_diagnostics" in compiled
        assert "diagnostic_run" in compiled
