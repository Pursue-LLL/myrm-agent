"""Capacity Theater Memory Doctor probe and Disciplined Defaults restoration tests.

[INPUT]
app.services.memory.diagnostics.diagnostic.diagnostic_static_checks::probe_capacity_theater
app.services.memory.diagnostics.diagnostic.diagnostic_repair_executor::MemoryDiagnosticRepairExecutor

[OUTPUT]
test_capacity_theater_probe_clean, test_capacity_theater_probe_bloated,
test_restore_disciplined_defaults_execution,
test_restore_disciplined_defaults_without_memory_backend

[POS]
Integration tests proving capacity theater detection and zero-data-loss safe archive
restoration through the real Memory Doctor repair executor, a real embedded Qdrant store
and a real SQLite relational store. The restoration path is only reachable via
`/command-center/diagnostics/repairs`, so the executor — not a duplicate helper — is the
contract under test. Only the embedding transport is substituted with a deterministic
local embedder so the suite needs neither provider credentials nor network access.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from myrm_agent_harness.toolkits.memory import MemoryType
from myrm_agent_harness.toolkits.memory.config import MemoryConfig
from myrm_agent_harness.toolkits.memory.manager import MemoryManager
from myrm_agent_harness.toolkits.memory.setup import create_local_memory_manager
from myrm_agent_harness.toolkits.memory.types import MemoryStatus, SemanticMemory
from myrm_agent_harness.toolkits.retriever.embedding.factory import EmbeddingConfig
from myrm_agent_harness.toolkits.vector.qdrant.factory import clear_embedded_stores
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.database.models import Base
from app.services.memory.diagnostics.diagnostic.diagnostic_repair_executor import (
    MemoryDiagnosticRepairExecutor,
)
from app.services.memory.diagnostics.diagnostic.diagnostic_static_checks import (
    probe_capacity_theater,
)

pytestmark = pytest.mark.integration

_ARCHIVED_TYPES = (MemoryType.TASK_DIGEST, MemoryType.CONVERSATION, MemoryType.SEMANTIC)
_EMBEDDING_DIMENSION = 768


class _DeterministicEmbeddingService:
    """Offline embedder: distinct content maps to distinct vectors, identical content collapses.

    Determinism matters here — the repair sweep asserts on memory identity and lifecycle,
    never on semantic ranking, so a stable hash-derived unit vector is sufficient and
    removes the paid-provider dependency that previously made this suite non-hermetic.
    """

    dimension = _EMBEDDING_DIMENSION

    @staticmethod
    def _vector(text: str) -> list[float]:
        seed = sum(ord(ch) * (idx + 1) for idx, ch in enumerate(text)) or 1
        return [((seed * (i + 1)) % 997) / 997.0 for i in range(_EMBEDDING_DIMENSION)]

    async def embed(self, text: str) -> list[float]:
        return self._vector(text)

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(text) for text in texts]


@pytest.fixture(autouse=True)
async def _reset_embedded_stores():
    """Release real embedded Qdrant singletons between cases."""
    await clear_embedded_stores()
    yield
    await clear_embedded_stores()


@pytest.fixture
async def db_session():
    """In-memory SQLite session with the server ORM schema applied."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine.sync_engine, "connect")
    def _enable_foreign_keys(dbapi_conn, _record) -> None:
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with factory() as session:
            yield session
    finally:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()


@pytest.fixture
async def memory_manager(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, db_session: AsyncSession):
    """Real MemoryManager on real embedded Qdrant + SQLite; only embeddings are offline."""
    _ = db_session
    from myrm_agent_harness.toolkits.memory import setup as memory_setup

    monkeypatch.setattr(
        memory_setup,
        "get_embedding_service",
        lambda *_args, **_kwargs: _DeterministicEmbeddingService(),
    )
    manager = await create_local_memory_manager(
        base_path=tmp_path / "memory",
        embedding_config=EmbeddingConfig(model="local/deterministic"),
        user_id="capacity-theater-user",
    )
    try:
        yield manager
    finally:
        await manager.close()


def _semantic(content: str) -> SemanticMemory:
    """Semantic content only; the store assigns the deterministic memory id, so callers use the result."""
    return SemanticMemory(content=content)


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
    assert "restore_disciplined_defaults" in check.repair_actions


@pytest.mark.asyncio
async def test_restore_disciplined_defaults_execution(
    db_session: AsyncSession, memory_manager: MemoryManager
) -> None:
    """Verify the real repair plan archives unpinned memories while preserving pinned ones."""
    pinned = await memory_manager.store(_semantic("Keep the release checklist pinned."))
    unpinned = await memory_manager.store(_semantic("Temporary working note to archive."))
    await memory_manager.pin_memory(pinned.id)

    executor = MemoryDiagnosticRepairExecutor(db_session, memory_manager)
    result, run = await executor.run("restore_disciplined_defaults", "execute")

    assert result.status == "completed"
    assert result.changed is True
    assert "archived 1 memories" in result.message
    assert "preserved 1 pinned entries" in result.message
    # The executor must rerun diagnostics so the GUI trend reflects the repair.
    assert run is not None

    # Data-level proof: the unpinned memory is archived, the pinned one survives the sweep.
    for memory_type in _ARCHIVED_TYPES:
        for item in await memory_manager.list_memories(memory_type, limit=50, include_archived=True):
            if item.id == unpinned.id:
                assert item.status == MemoryStatus.ARCHIVED, item
            if item.id == pinned.id:
                assert item.status == MemoryStatus.ACTIVE, item

    active_ids = {
        item.id
        for memory_type in _ARCHIVED_TYPES
        for item in await memory_manager.list_memories(memory_type, limit=50)
    }
    assert pinned.id in active_ids
    assert unpinned.id not in active_ids

    # Dry-run remains side-effect free.
    dry_result, dry_run = await executor.run("restore_disciplined_defaults", "dry_run")
    assert dry_result.status == "dry_run"
    assert dry_result.changed is False
    assert dry_run is None


@pytest.mark.asyncio
async def test_restore_disciplined_defaults_without_memory_backend(db_session: AsyncSession) -> None:
    """A manager without a vector backend must not crash the repair plan."""
    manager = MemoryManager(
        MemoryConfig(embedding_model="local/deterministic"),
        user_id="capacity-theater-no-vector",
        embedding=_DeterministicEmbeddingService(),
        auto_warmup=False,
    )
    try:
        executor = MemoryDiagnosticRepairExecutor(db_session, manager)
        result, run = await executor.run("restore_disciplined_defaults", "execute")

        assert result.status == "completed"
        assert "archived 0 memories" in result.message
        assert "preserved 0 pinned entries" in result.message
        assert run is not None
    finally:
        await manager.close()


@pytest.mark.asyncio
async def test_restore_disciplined_defaults_reports_partial_failures(
    db_session: AsyncSession, memory_manager: MemoryManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A per-memory archive failure must be surfaced, not silently reported as success."""
    await memory_manager.store(_semantic("Sweep target that fails to archive."))

    original_update = memory_manager.update_memory

    async def _failing_update(memory_id: str, **kwargs) -> None:
        if kwargs.get("status") == MemoryStatus.ARCHIVED:
            raise RuntimeError("simulated archive backend failure")
        return await original_update(memory_id, **kwargs)

    monkeypatch.setattr(memory_manager, "update_memory", _failing_update)

    executor = MemoryDiagnosticRepairExecutor(db_session, memory_manager)
    result, _ = await executor.run("restore_disciplined_defaults", "execute")

    assert result.status == "completed"
    assert "archived 0 memories" in result.message
    # Silence here would let an operator read a failed sweep as a completed repair.
    assert "1 entries could not be archived" in result.message
