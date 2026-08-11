"""Memory Doctor diagnostics full-chain integration test.

Covers the real write-read consistency path end to end:

1. POST /memory/command-center/diagnostics/actions with action=run_diagnostics executes the
   golden recall benchmark against a real MemoryManager backed by a real embedding provider
   (BAAI/bge-m3 via SiliconFlow, configured in .env.test). The benchmark measures latency
   p50/p95 with perf_counter and the service persists the flattened metrics (including
   benchmark_categories and embedding_model) into the operation ledger.
2. GET /memory/command-center/diagnostics/history projects the ledger row back into a
   trend-ready history item whose benchmark reconstructs latency/categories/embedding model.

The critical path (real benchmark measurement) is deliberately NOT mocked.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from unittest.mock import patch

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database.models import Base
from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="memory")


@pytest_asyncio.fixture
async def db_session(tmp_path: Path) -> AsyncIterator[AsyncSession]:
    db_path = tmp_path / "test.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


def _patch_memory_path(path: str) -> patch:
    """Point settings database paths at a temp dir so vector store stays out of user data."""
    qdrant_path = str(Path(path) / "vector_store")
    return patch.multiple(
        "app.config.settings.settings.database",
        memory_base_path=path,
        qdrant_path=qdrant_path,
    )


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_diagnostic_run_history_roundtrip_with_real_embedding(
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    """Real diagnostics run persists latency and history projects it back."""
    from myrm_agent_harness.toolkits.retriever.embedding.factory import EmbeddingConfig
    from myrm_agent_harness.toolkits.vector.qdrant import clear_embedded_stores

    from app.api.dependencies import get_db_session, get_deploy_identity
    from app.api.memory.utils import get_crud_memory_manager
    from app.core.memory.adapters.setup import create_memory_manager, resolve_context_binding

    embedding_cfg = EmbeddingConfig(
        model="BAAI/bge-m3",
        api_key="sk-nznibczsofctvcsavtubpsgtyhqxijdsspzcvwypkouawunz",
        api_base="https://api.siliconflow.cn/v1",
    )

    async def _session_override() -> AsyncIterator[AsyncSession]:
        yield db_session

    manager = None

    async def _manager_override() -> AsyncIterator[object]:
        yield manager

    app.dependency_overrides[get_deploy_identity] = lambda: {"id": "test_user", "username": "test"}
    app.dependency_overrides[get_db_session] = _session_override
    app.dependency_overrides[get_crud_memory_manager] = _manager_override

    try:
        manager = await create_memory_manager(
            resolve_context_binding(
                namespaces=None,
                agent_id=None,
                channel_id=None,
                conversation_id=None,
                task_id=None,
            ),
            embedding_config=embedding_cfg,
            base_path=tmp_path / "memory",
        )
        with patch("app.core.security.auth.identity.is_loopback_ip", return_value=True):
            client = TestClient(app)
            run_resp = client.post(
                "/api/v1/memory/command-center/diagnostics/actions",
                json={"action": "run_diagnostics"},
            )
            assert run_resp.status_code == 200, run_resp.text
            probes = run_resp.json()["run"]["probes"]
            benchmark = next((p for p in probes if p["id"] == "golden_recall_benchmark"), None)
            assert benchmark is not None, [p["id"] for p in probes]
            summary = benchmark.get("benchmark_summary")
            assert summary is not None, benchmark.get("evidence")
            assert summary["case_count"] > 0
            assert summary["latency_p50_ms"] > 0
            assert summary["latency_p95_ms"] >= summary["latency_p50_ms"]
            assert summary["categories"], "categories must persist for trend localization"

            history_resp = client.get("/api/v1/memory/command-center/diagnostics/history")
            assert history_resp.status_code == 200
            items = history_resp.json()["items"]
            assert items, "history must include the just-completed run"
            latest = items[0]
            assert latest["benchmark"] is not None
            assert latest["benchmark"]["latency_p50_ms"] > 0
            assert latest["benchmark"]["latency_p95_ms"] > 0
            assert latest["benchmark"]["categories"], "categories reconstructed from ledger metadata"
            assert latest["benchmark"]["recall_at_k"] == summary["recall_at_k"]
            assert latest["embedding_model"], "embedding model persisted and projected"
    finally:
        app.dependency_overrides.clear()
        await clear_embedded_stores()


@pytest.mark.asyncio
async def test_diagnostic_history_empty_db_returns_empty_items(
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    """Empty ledger returns an empty history list (no phantom entries)."""
    from app.api.dependencies import get_db_session, get_deploy_identity

    async def _session_override() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_deploy_identity] = lambda: {"id": "test_user", "username": "test"}
    app.dependency_overrides[get_db_session] = _session_override
    try:
        with patch("app.core.security.auth.identity.is_loopback_ip", return_value=True):
            client = TestClient(app)
            resp = client.get("/api/v1/memory/command-center/diagnostics/history")
        assert resp.status_code == 200
        assert resp.json()["items"] == []
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_diagnostic_history_orders_and_limits_with_nested_metadata(
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    """History is newest-first, limit slices, and nested categories survive the round trip."""
    from myrm_agent_harness.toolkits.memory import MemoryOperationKind, MemoryOperationStatus

    from app.api.dependencies import get_db_session, get_deploy_identity
    from app.services.memory.operation_ledger import MemoryOperationLedgerService

    ledger = MemoryOperationLedgerService(db_session)
    await ledger.record_event(
        kind=MemoryOperationKind.HEALTH_CHECK,
        status=MemoryOperationStatus.SUCCESS,
        summary="older run",
        source="memory_diagnostics",
        target_kind="health",
        target_id="diagnostic_run",
        metadata={
            "benchmark_recall_at_k": 0.5,
            "benchmark_latency_p50_ms": 10.0,
            "benchmark_categories": {"profile": "2/2", "procedural": "1/2"},
        },
        commit=True,
    )
    await ledger.record_event(
        kind=MemoryOperationKind.HEALTH_CHECK,
        status=MemoryOperationStatus.SUCCESS,
        summary="newer run",
        source="memory_diagnostics",
        target_kind="health",
        target_id="diagnostic_run",
        metadata={
            "benchmark_recall_at_k": 0.9,
            "benchmark_latency_p50_ms": 20.0,
        },
        commit=True,
    )

    async def _session_override() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_deploy_identity] = lambda: {"id": "test_user", "username": "test"}
    app.dependency_overrides[get_db_session] = _session_override
    try:
        with patch("app.core.security.auth.identity.is_loopback_ip", return_value=True):
            client = TestClient(app)
            all_resp = client.get("/api/v1/memory/command-center/diagnostics/history")
            limited_resp = client.get("/api/v1/memory/command-center/diagnostics/history?limit=1")
        assert all_resp.status_code == 200
        items = all_resp.json()["items"]
        assert len(items) == 2
        assert items[0]["benchmark"]["recall_at_k"] == 0.9
        assert items[0]["benchmark"]["latency_p50_ms"] == 20.0
        assert items[0]["benchmark"]["categories"] == {}
        assert items[1]["benchmark"]["categories"] == {"profile": "2/2", "procedural": "1/2"}

        assert limited_resp.status_code == 200
        limited = limited_resp.json()["items"]
        assert len(limited) == 1
        assert limited[0]["benchmark"]["recall_at_k"] == 0.9
    finally:
        app.dependency_overrides.clear()
