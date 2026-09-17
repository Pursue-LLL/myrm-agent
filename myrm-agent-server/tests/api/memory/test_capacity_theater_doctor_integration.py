"""Unit and integration tests for Capacity Theater Memory Doctor probe and Disciplined Defaults restoration.

[INPUT]
app.services.memory.diagnostics.diagnostic.diagnostic_static_checks::probe_capacity_theater
app.services.memory.diagnostics.diagnostic.diagnostic_repair_executor::MemoryDiagnosticRepairExecutor

[OUTPUT]
test_capacity_theater_probe_clean, test_capacity_theater_probe_bloated, test_restore_disciplined_defaults_execution

[POS]
Integration tests proving capacity theater detection and zero-data-loss safe archive restoration.
The restoration case drives the *production* repair executor against a real MemoryManager
(local SQLite + embedded Qdrant + fake embedding), so the archive/preserve contract and the
pinned predicate are verified end to end instead of against mocks.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from myrm_agent_harness.toolkits.memory.config import MemoryConfig
from myrm_agent_harness.toolkits.memory.manager import MemoryManager
from myrm_agent_harness.toolkits.memory.setup import create_local_memory_manager
from myrm_agent_harness.toolkits.memory.types import MemoryStatus
from myrm_agent_harness.toolkits.vector.qdrant.factory import (
    clear_embedded_stores,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database.models import Base
from app.services.memory.diagnostics.diagnostic.diagnostic_repair_executor import (
    MemoryDiagnosticRepairExecutor,
)
from app.services.memory.diagnostics.diagnostic.diagnostic_static_checks import probe_capacity_theater

_RESTORE_PLAN_ID = "restore_disciplined_defaults"


@pytest.fixture
async def db_session_factory():
    """Real SQLite session factory with the full product schema created."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


@pytest.fixture(autouse=True)
async def _clear_embedded_cache():
    """Release real embedded Qdrant singletons between cases."""
    await clear_embedded_stores()
    yield
    await clear_embedded_stores()


def test_capacity_theater_probe_clean() -> None:
    """Verify clean memory stack returns ready status and no auto fix."""
    check = probe_capacity_theater(
        total_active_chars=1200,
        working_memory_count=5,
        unpinned_count=10,
        budget_limit=6000,
    )
    assert check.id == "capacity_theater"
    assert check.status == "ready"
    assert check.can_auto_fix is False
    assert check.repair_actions == []


def test_capacity_theater_probe_bloated() -> None:
    """Verify bloated memory stack returns warning status and restore repair action."""
    check = probe_capacity_theater(
        total_active_chars=7500,
        working_memory_count=45,
        unpinned_count=60,
        budget_limit=6000,
    )
    assert check.id == "capacity_theater"
    assert check.status == "warning"
    assert check.can_auto_fix is True
    assert _RESTORE_PLAN_ID in check.repair_actions


class _FakeEmbedding:
    """Deterministic embedding stub: the storage contract, not the model, is under test."""

    dimension = 64

    async def embed(self, text: str) -> list[float]:
        return [0.1] * self.dimension

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [[0.1] * self.dimension for _ in texts]


@pytest.mark.asyncio
async def test_restore_disciplined_defaults_execution(
    db_session_factory,
    tmp_path: Path,
) -> None:
    """Real executor + real storage: unpinned memories are archived, pinned ones preserved."""
    manager = await create_local_memory_manager(
        base_path=str(tmp_path / "memory"),
        embedding_config=MemoryConfig(embedding_model="openai/text-embedding-3-small"),
    )
    try:
        pinned = await manager.add_knowledge("User prefers Rust for CLI tooling.", importance=0.9)
        unpinned = await manager.add_knowledge("Transient scratch note about a draft plan.", importance=0.3)
        await manager.pin_memory(pinned.id)

        async with db_session_factory() as db:
            executor = MemoryDiagnosticRepairExecutor(db, manager)
            result, run = await executor.run(_RESTORE_PLAN_ID, "execute")

        assert result.status == "completed"
        assert result.changed is True
        assert "archived 1 memories" in result.message
        assert "preserved 1 pinned entries" in result.message
        assert run is not None

        stored_pinned = await manager.get_memory(pinned.id)
        stored_unpinned = await manager.get_memory(unpinned.id)
        assert stored_pinned is not None and stored_pinned.status is MemoryStatus.ACTIVE
        assert stored_pinned.pinned is True
        assert stored_unpinned is not None and stored_unpinned.status is MemoryStatus.ARCHIVED
    finally:
        await manager.close()


@pytest.mark.asyncio
async def test_restore_disciplined_defaults_respects_rule_lock(
    db_session_factory,
    tmp_path: Path,
) -> None:
    """A user-locked rule must never be archived by an automated repair."""
    manager = await create_local_memory_manager(
        base_path=str(tmp_path / "memory"),
        embedding_config=MemoryConfig(embedding_model="openai/text-embedding-3-small"),
    )
    try:
        rule = await manager.add_rule("Always answer in Chinese.", is_user_locked=True)

        async with db_session_factory() as db:
            executor = MemoryDiagnosticRepairExecutor(db, manager)
            result, _ = await executor.run(_RESTORE_PLAN_ID, "execute")

        assert result.status == "completed"
        assert "archived 0 memories" in result.message
        stored_rule = await manager.get_memory(rule.id)
        assert stored_rule is not None
        assert stored_rule.is_user_protected is True
    finally:
        await manager.close()


class _StubMemoryManager(MemoryManager):
    """Shared-layer stub: counts archives without touching storage (plan-accounting contract)."""

    def __init__(self, items: list[object]) -> None:
        self._items = items
        self.archived_ids: list[str] = []

    async def list_memories(self, memory_type: object, *, limit: int = 100) -> list[object]:
        from myrm_agent_harness.toolkits.memory import MemoryType

        return list(self._items) if memory_type is MemoryType.SEMANTIC else []

    async def update_memory(self, memory_id: str, **kwargs: object) -> None:
        assert kwargs.get("status") is MemoryStatus.ARCHIVED
        self.archived_ids.append(memory_id)


@pytest.mark.asyncio
async def test_restore_disciplined_defaults_counts_pinned_predicate(db_session_factory) -> None:
    """Pinned accounting must read the harness ``pinned`` flag, not a legacy ``is_pinned`` alias."""
    from types import SimpleNamespace

    pinned = SimpleNamespace(id="mem-pinned", pinned=True, is_user_locked=False)
    unlocked = SimpleNamespace(id="mem-unpinned", pinned=False, is_user_locked=False)
    manager = _StubMemoryManager([pinned, unlocked])

    async with db_session_factory() as db:
        executor = MemoryDiagnosticRepairExecutor(db, manager)
        result, _ = await executor.run(_RESTORE_PLAN_ID, "execute")

    assert "archived 1 memories" in result.message
    assert "preserved 1 pinned entries" in result.message
    assert manager.archived_ids == ["mem-unpinned"]
