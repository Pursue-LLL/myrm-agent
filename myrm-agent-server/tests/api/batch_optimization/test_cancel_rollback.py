"""RollbackService orchestration and HTTP cancel keep-strategy contract tests."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database.connection import get_db
from app.database.models import Base, BatchSnapshot
from app.services.skill_optimization.rollback_service import RollbackResult, RollbackService
from tests.api.batch_optimization.support import (
    AuditLogRepositoryStub,
    BatchTaskRepositoryStub,
    FakeBatchTask,
    batch_router_module,
)


@pytest.mark.asyncio
async def test_rollback_service_restores_all_snapshots() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        session.add(
            BatchSnapshot(
                snapshot_id="snap-1",
                batch_id="batch-rollback-1",
                skill_id="skill-a",
                skill_content_before="content-a-v1",
                skill_version_before=1,
                skill_metadata={},
            )
        )
        session.add(
            BatchSnapshot(
                snapshot_id="snap-2",
                batch_id="batch-rollback-1",
                skill_id="skill-b",
                skill_content_before="content-b-v2",
                skill_version_before=2,
                skill_metadata={},
            )
        )
        await session.commit()

        restored: list[tuple[str, str, int]] = []

        async def skill_writer(skill_id: str, content: str, version: int) -> None:
            restored.append((skill_id, content, version))

        service = RollbackService(session)
        result = await service.rollback_batch("batch-rollback-1", skill_writer)

    assert result.success is True
    assert result.total_skills == 2
    assert result.rolled_back == 2
    assert result.failed == 0
    assert sorted(restored) == [
        ("skill-a", "content-a-v1", 1),
        ("skill-b", "content-b-v2", 2),
    ]


@pytest.mark.asyncio
async def test_rollback_batch_partial_failure_marks_success_false() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    batch_id = "batch-rollback-partial"

    async with session_factory() as session:
        session.add(
            BatchSnapshot(
                snapshot_id="snap-partial-a",
                batch_id=batch_id,
                skill_id="skill-a",
                skill_content_before="content-a",
                skill_version_before=1,
                skill_metadata={},
            )
        )
        session.add(
            BatchSnapshot(
                snapshot_id="snap-partial-b",
                batch_id=batch_id,
                skill_id="skill-b",
                skill_content_before="content-b",
                skill_version_before=2,
                skill_metadata={},
            )
        )
        await session.commit()

        restored: list[str] = []

        async def skill_writer(skill_id: str, content: str, version: int) -> None:
            if skill_id == "skill-b":
                raise OSError("disk write failed")
            restored.append(skill_id)

        service = RollbackService(session)
        result = await service.rollback_batch(batch_id, skill_writer)

    assert result.success is False
    assert result.total_skills == 2
    assert result.rolled_back == 1
    assert result.failed == 1
    assert restored == ["skill-a"]


def test_cancel_keep_skips_rollback(
    batch_client: TestClient,
    batch_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task = FakeBatchTask(
        batch_id="batch-cancel-2",
        max_concurrent=2,
        status="pending",
        skill_ids={"ids": ["skill-a", "skill-b"]},
        total_tasks=2,
    )
    repo_stub = BatchTaskRepositoryStub(task)
    audit_stub = AuditLogRepositoryStub()

    rollback_invoked = False

    class RollbackServiceStub:
        def __init__(self, session: object) -> None:
            self.session = session

        async def rollback_batch(self, batch_id: str, skill_writer: object) -> RollbackResult:
            nonlocal rollback_invoked
            rollback_invoked = True
            return RollbackResult(success=True, total_skills=0, rolled_back=0, failed=0)

    async def mock_get_db():
        yield AsyncMock()

    batch_app.dependency_overrides[get_db] = mock_get_db
    monkeypatch.setattr(batch_router_module, "BatchTaskRepository", lambda _s: repo_stub)
    monkeypatch.setattr(batch_router_module, "AuditLogRepository", lambda _s: audit_stub)
    monkeypatch.setattr(batch_router_module, "RollbackService", RollbackServiceStub)
    monkeypatch.setattr(
        "app.core.infra.server_globals.get_optimization_scheduler",
        lambda: None,
    )

    response = batch_client.post(
        "/api/v1/batch-optimization/tasks/batch-cancel-2/cancel",
        json={"cleanup_strategy": "keep"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["rollback_performed"] is False
    assert rollback_invoked is False


def test_cancel_invokes_scheduler_cancel_batch_optimization(
    batch_client: TestClient,
    batch_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task = FakeBatchTask(batch_id="batch-cancel-scheduler-1", max_concurrent=2, status="running")
    repo_stub = BatchTaskRepositoryStub(task)
    audit_stub = AuditLogRepositoryStub()
    cancelled_batches: list[str] = []

    class SchedulerStub:
        async def cancel_batch_optimization(self, batch_id: str) -> bool:
            cancelled_batches.append(batch_id)
            return True

        async def await_batch_optimization(self, batch_id: str, timeout: float = 120.0) -> bool:
            return True

    async def mock_get_db():
        yield AsyncMock()

    batch_app.dependency_overrides[get_db] = mock_get_db
    monkeypatch.setattr(batch_router_module, "BatchTaskRepository", lambda _s: repo_stub)
    monkeypatch.setattr(batch_router_module, "AuditLogRepository", lambda _s: audit_stub)
    monkeypatch.setattr(
        "app.core.infra.server_globals.get_optimization_scheduler",
        lambda: SchedulerStub(),
    )

    response = batch_client.post(
        "/api/v1/batch-optimization/tasks/batch-cancel-scheduler-1/cancel",
        json={"cleanup_strategy": "keep"},
    )

    assert response.status_code == 200
    assert cancelled_batches == ["batch-cancel-scheduler-1"]


def test_cancel_skips_rollback_when_await_times_out(
    batch_client: TestClient,
    batch_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task = FakeBatchTask(batch_id="batch-cancel-await-timeout", max_concurrent=2, status="running")
    repo_stub = BatchTaskRepositoryStub(task)
    audit_stub = AuditLogRepositoryStub()
    rollback_invoked = False

    class RollbackServiceStub:
        def __init__(self, session: object) -> None:
            self.session = session

        async def rollback_batch(self, batch_id: str, skill_writer: object) -> RollbackResult:
            nonlocal rollback_invoked
            rollback_invoked = True
            return RollbackResult(success=True, total_skills=0, rolled_back=0, failed=0)

    class SchedulerStub:
        async def cancel_batch_optimization(self, batch_id: str) -> bool:
            return True

        async def await_batch_optimization(self, batch_id: str, timeout: float = 120.0) -> bool:
            return False

    async def mock_get_db():
        yield AsyncMock()

    batch_app.dependency_overrides[get_db] = mock_get_db
    monkeypatch.setattr(batch_router_module, "BatchTaskRepository", lambda _s: repo_stub)
    monkeypatch.setattr(batch_router_module, "AuditLogRepository", lambda _s: audit_stub)
    monkeypatch.setattr(batch_router_module, "RollbackService", RollbackServiceStub)
    monkeypatch.setattr(
        "app.core.infra.server_globals.get_optimization_scheduler",
        lambda: SchedulerStub(),
    )

    response = batch_client.post(
        "/api/v1/batch-optimization/tasks/batch-cancel-await-timeout/cancel",
        json={"cleanup_strategy": "rollback"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["rollback_performed"] is False
    assert body["rolled_back"] == 0
    assert body["error_message"] is not None
    assert "did not stop in time" in body["error_message"]
    assert rollback_invoked is False
