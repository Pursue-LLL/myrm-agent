"""Memory Doctor store checks: capacity sampling and relational integrity, snapshot and run alike.

[INPUT]
app.services.memory.diagnostics.diagnostics::MemoryDiagnosticsService (POS: 诊断服务，快照与运行共用同一份存储检查)
app.schemas.memory.command_center::MemoryCommandRuntimeStatus (POS: deployment and storage status)

[OUTPUT]
Capacity counts, partial counts after a failed read, relational integrity outcomes, and the
guarantee that the diagnostic run reports the same capacity and relational results as the snapshot.

[POS]
Pins the sampling and integrity behaviour that `build_doctor_checks` and `run_diagnostics` share,
so the two entry points cannot drift apart.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock

import pytest
from myrm_agent_harness.toolkits.memory import MemoryManager
from myrm_agent_harness.toolkits.memory.types import MemoryType
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.memory.command_center import MemoryCommandDiagnosticProbeResult, MemoryCommandRuntimeStatus
from app.services.memory.diagnostics import diagnostics as diagnostics_module
from app.services.memory.diagnostics.diagnostics import MemoryDiagnosticsService
from app.services.memory.ledger.operation_ledger import MemoryOperationLedgerService

type Integrity = Callable[[], Awaitable[tuple[bool, str]]]


class _StoreManager:
    """Only what the store checks and the retrieval probes read from a memory manager."""

    has_vector = True
    last_retrieval_trace = None
    config = SimpleNamespace(bm25_top_k=20, bm25_max_corpus_size=5000, embedding_model="m-1")

    def __init__(
        self,
        items: Mapping[MemoryType, list[SimpleNamespace]] | None = None,
        *,
        fail_at: MemoryType | None = None,
        integrity: Integrity | None = None,
    ) -> None:
        self._items = items or {}
        self._fail_at = fail_at
        if integrity is not None:
            self._relational = SimpleNamespace(check_integrity=integrity)

    async def list_memories(self, mtype: MemoryType, limit: int = 20) -> list[SimpleNamespace]:
        _ = limit
        if mtype == self._fail_at:
            raise RuntimeError("list boom")
        return self._items.get(mtype, [])

    def get_enabled_types(self) -> list[MemoryType]:
        return [MemoryType.SEMANTIC]

    async def search(self, query: str, **kwargs: object) -> list[object]:
        _ = (query, kwargs)
        return []


def _runtime() -> MemoryCommandRuntimeStatus:
    return MemoryCommandRuntimeStatus.model_validate(
        {
            "deploy_mode": "local",
            "memory_base_path": "/tmp/memory",
            "relational_status": "available",
            "vector_status": "available",
            "vector_persistence": "persistent",
            "graph_status": "available",
            "embedding_status": "custom",
            "retrieval_mode": "semantic",
            "control_plane_status": "not_used",
            "event_ledger_status": "available",
            "health_snapshot_status": "available",
            "supported_clients": ["local_web"],
        }
    )


def _db() -> AsyncSession:
    # No migration rows: the migration check reports pending, which these tests do not look at.
    result = SimpleNamespace(fetchall=list)
    return cast(AsyncSession, SimpleNamespace(execute=AsyncMock(return_value=result), rollback=AsyncMock()))


def _service(manager: _StoreManager | None) -> MemoryDiagnosticsService:
    ledger = SimpleNamespace(record_event=AsyncMock(), list_events=AsyncMock(return_value=[]))
    return MemoryDiagnosticsService(
        _db(),
        cast(MemoryManager | None, manager),
        ledger=cast(MemoryOperationLedgerService, ledger),
    )


async def _snapshot_check(manager: _StoreManager | None, check_id: str) -> tuple[str, str]:
    checks = await _service(manager).build_doctor_checks(health_cache_status="fresh", runtime=_runtime())
    check = next(c for c in checks if c.id == check_id)
    return check.status, check.evidence


def _item(content: str | None = None, *, pinned: bool | None = None) -> SimpleNamespace:
    """Memory rows are read with getattr defaults, so absent attributes must be tolerated."""
    attrs: dict[str, object] = {}
    if content is not None:
        attrs["content"] = content
    if pinned is not None:
        attrs["pinned"] = pinned
    return SimpleNamespace(**attrs)


async def _ok_integrity() -> tuple[bool, str]:
    return True, "ok"


async def _corrupt_integrity() -> tuple[bool, str]:
    return False, "page corrupt"


async def _raising_integrity() -> tuple[bool, str]:
    raise RuntimeError("db locked")


@pytest.mark.asyncio
async def test_capacity_is_ready_without_a_memory_manager() -> None:
    status, evidence = await _snapshot_check(None, "capacity_theater")

    assert status == "ready"
    assert evidence == "Disciplined memory load within budget: 0/6000 chars."


@pytest.mark.asyncio
async def test_capacity_counts_chars_session_memories_and_unpinned_entries() -> None:
    rows = [_item("x" * 4000, pinned=False), _item("y" * 10, pinned=True), _item(None), _item(pinned=True)]
    manager = _StoreManager({mtype: rows for mtype in MemoryType})

    status, evidence = await _snapshot_check(manager, "capacity_theater")

    # Four sampled types x 4010 chars; only task digests and conversations count as session memories;
    # a row without a `pinned` attribute counts as unpinned.
    assert status == "warning"
    assert evidence == "Active memory load: 16040/6000 chars, 8 session memories, 8 unpinned entries."


@pytest.mark.asyncio
async def test_capacity_keeps_the_counts_gathered_before_a_read_fails() -> None:
    manager = _StoreManager(
        {
            MemoryType.PROFILE: [_item("a" * 3000, pinned=False) for _ in range(3)],
            MemoryType.TASK_DIGEST: [_item("b" * 7, pinned=False), _item("c", pinned=True)],
        },
        fail_at=MemoryType.CONVERSATION,
    )

    status, evidence = await _snapshot_check(manager, "capacity_theater")

    assert status == "warning"
    assert evidence == "Active memory load: 9008/6000 chars, 2 session memories, 4 unpinned entries."


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("integrity", "status", "detail"),
    [
        (_ok_integrity, "ready", "passed integrity verification"),
        (_corrupt_integrity, "critical", "page corrupt"),
        (_raising_integrity, "critical", "db locked"),
        (None, "ready", "passed integrity verification"),
    ],
    ids=["ok", "corrupt", "raises", "manager-without-relational-store"],
)
async def test_relational_store_reports_the_integrity_outcome(integrity: Integrity | None, status: str, detail: str) -> None:
    got_status, evidence = await _snapshot_check(_StoreManager(integrity=integrity), "relational_store")

    assert got_status == status
    assert detail in evidence


def _stub_probe(probe_id: str) -> Callable[..., Awaitable[MemoryCommandDiagnosticProbeResult]]:
    async def _probe(*_args: object, **_kwargs: object) -> MemoryCommandDiagnosticProbeResult:
        return MemoryCommandDiagnosticProbeResult(
            id=probe_id,
            category="index",
            label=probe_id,
            status="ready",
            evidence="stub",
            impact="stub",
            next_action="stub",
            safe_to_retry=True,
            duration_ms=0.0,
            repair_actions=[],
        )

    return _probe


@pytest.mark.asyncio
async def test_diagnostic_run_reports_the_same_store_checks_as_the_snapshot(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, probe_id in (
        ("run_embedding_live_probe", "embedding_live"),
        ("run_golden_recall_benchmark", "golden_recall_benchmark"),
        ("run_memory_quality_probe", "memory_quality_governance"),
    ):
        monkeypatch.setattr(diagnostics_module, name, _stub_probe(probe_id))
    manager = _StoreManager(
        {MemoryType.PROFILE: [_item("a" * 7000, pinned=False)]},
        fail_at=MemoryType.CONVERSATION,
        integrity=_corrupt_integrity,
    )

    run = await _service(manager).run_diagnostics(health_cache_status="fresh", runtime=_runtime())

    probes = {probe.id: probe for probe in run.probes}
    for check_id in ("capacity_theater", "relational_store"):
        status, evidence = await _snapshot_check(manager, check_id)
        assert (probes[check_id].status, probes[check_id].evidence) == (status, evidence)
    assert probes["capacity_theater"].status == "warning"
    assert probes["relational_store"].status == "critical"
