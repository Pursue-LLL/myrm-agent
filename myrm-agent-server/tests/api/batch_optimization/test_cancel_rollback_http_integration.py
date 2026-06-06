"""HTTP integration tests: cancel rollback uses real RollbackService + disk restore."""

from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from myrm_agent_harness.agent.skills.optimization.types import (
    SkillQualityScore,
    SkillVersion,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.core.skills.config_version as config_version
from app.database.connection import get_db
from app.database.models import Base, BatchSnapshot
from app.services.skill_optimization.rollback_service import RollbackService
from tests.api.batch_optimization.support import (
    AuditLogRepositoryStub,
    BatchTaskRepositoryStub,
    FakeBatchTask,
    batch_router_module,
)


def _sample_version(skill_id: str, version: int, content: str) -> SkillVersion:
    return SkillVersion(
        skill_id=skill_id,
        version=version,
        content=content,
        quality_score=SkillQualityScore(
            success_rate=0.5,
            token_efficiency=0.5,
            execution_time=0.5,
            user_satisfaction=0.5,
            call_frequency=0.5,
        ),
        created_at=datetime(2026, 1, 1),
        created_by="test",
        optimization_id=None,
        is_active=False,
        metadata=None,
    )


@pytest.mark.asyncio
async def test_create_batch_snapshot_persists_rows() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    batch_id = "batch-snapshot-http-1"
    content_before = "# Skill before optimization"

    async with session_factory() as session:
        service = RollbackService(session)

        async def skill_reader(skill_id: str) -> tuple[str, int, dict[str, object]]:
            return content_before, 2, {"skill_id": skill_id}

        ok = await service.create_batch_snapshot(
            batch_id=batch_id,
            skill_ids=["skill-a", "skill-b"],
            skill_reader=skill_reader,
        )
        assert ok is True

        result = await session.execute(select(BatchSnapshot).where(BatchSnapshot.batch_id == batch_id))
        rows = list(result.scalars().all())

    assert len(rows) == 2
    assert {row.skill_id for row in rows} == {"skill-a", "skill-b"}
    assert all(row.skill_content_before == content_before for row in rows)
    assert all(row.skill_version_before == 2 for row in rows)


def test_cancel_http_real_rollback_writes_disk(
    batch_client: TestClient,
    batch_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    batch_id = "batch-cancel-real-1"
    skill_id = "skill-a"
    content_before = "# Skill before batch cancel"
    skill_md = tmp_path / "SKILL.md"

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    async def init_db() -> async_sessionmaker[AsyncSession]:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with factory() as session:
            session.add(
                BatchSnapshot(
                    snapshot_id="snap-real-1",
                    batch_id=batch_id,
                    skill_id=skill_id,
                    skill_content_before=content_before,
                    skill_version_before=1,
                    skill_metadata={},
                )
            )
            await session.commit()
        return factory

    session_factory = asyncio.run(init_db())

    async def override_get_db():
        async with session_factory() as session:
            yield session

    storage = MagicMock()
    storage.get_skill_version = AsyncMock(return_value=_sample_version(skill_id, 1, content_before))
    storage.activate_version = AsyncMock(return_value=_sample_version(skill_id, 1, content_before))

    async def _resolve(_sid: str) -> Path:
        return skill_md

    monkeypatch.setattr(
        "app.services.skill_optimization.skill_version_sync.resolve_skill_md_path",
        _resolve,
    )
    monkeypatch.setattr(config_version, "bump_skill_config_version", lambda: None)

    task = FakeBatchTask(batch_id=batch_id, max_concurrent=2, status="running")
    repo_stub = BatchTaskRepositoryStub(task)
    audit_stub = AuditLogRepositoryStub()

    batch_app.dependency_overrides[get_db] = override_get_db
    monkeypatch.setattr(batch_router_module, "BatchTaskRepository", lambda _s: repo_stub)
    monkeypatch.setattr(batch_router_module, "AuditLogRepository", lambda _s: audit_stub)
    monkeypatch.setattr(batch_router_module, "get_storage", lambda: storage)
    monkeypatch.setattr(
        "app.core.infra.server_globals.get_optimization_scheduler",
        lambda: None,
    )

    response = batch_client.post(
        f"/api/v1/batch-optimization/tasks/{batch_id}/cancel",
        json={"cleanup_strategy": "rollback"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["rollback_performed"] is True
    assert body["status"] == "cancelled"
    assert skill_md.read_text(encoding="utf-8") == content_before
    storage.activate_version.assert_awaited_once_with(skill_id, 1)
    assert audit_stub.logs[0]["details"]["rollback_performed"] is True


def test_cancel_http_multi_skill_rollback_writes_disk(
    batch_client: TestClient,
    batch_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    batch_id = "batch-cancel-multi-1"
    skill_specs = {
        "skill-a": ("# Skill A before", 1),
        "skill-b": ("# Skill B before", 2),
    }
    skill_paths = {sid: tmp_path / sid / "SKILL.md" for sid in skill_specs}

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    async def init_db() -> async_sessionmaker[AsyncSession]:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with factory() as session:
            for index, (skill_id, (content, version)) in enumerate(skill_specs.items()):
                session.add(
                    BatchSnapshot(
                        snapshot_id=f"snap-multi-{index}",
                        batch_id=batch_id,
                        skill_id=skill_id,
                        skill_content_before=content,
                        skill_version_before=version,
                        skill_metadata={},
                    )
                )
            await session.commit()
        return factory

    session_factory = asyncio.run(init_db())

    async def override_get_db():
        async with session_factory() as session:
            yield session

    storage = MagicMock()

    async def _get_skill_version(skill_id: str, version: int) -> SkillVersion:
        content, ver = skill_specs[skill_id]
        return _sample_version(skill_id, ver, content)

    storage.get_skill_version = AsyncMock(side_effect=_get_skill_version)
    storage.activate_version = AsyncMock(side_effect=_get_skill_version)

    async def _resolve(skill_id: str) -> Path:
        return skill_paths[skill_id]

    monkeypatch.setattr(
        "app.services.skill_optimization.skill_version_sync.resolve_skill_md_path",
        _resolve,
    )
    monkeypatch.setattr(config_version, "bump_skill_config_version", lambda: None)

    task = FakeBatchTask(
        batch_id=batch_id,
        max_concurrent=2,
        status="running",
        skill_ids={"ids": list(skill_specs)},
        total_tasks=2,
    )
    repo_stub = BatchTaskRepositoryStub(task)
    audit_stub = AuditLogRepositoryStub()

    batch_app.dependency_overrides[get_db] = override_get_db
    monkeypatch.setattr(batch_router_module, "BatchTaskRepository", lambda _s: repo_stub)
    monkeypatch.setattr(batch_router_module, "AuditLogRepository", lambda _s: audit_stub)
    monkeypatch.setattr(batch_router_module, "get_storage", lambda: storage)
    monkeypatch.setattr(
        "app.core.infra.server_globals.get_optimization_scheduler",
        lambda: None,
    )

    response = batch_client.post(
        f"/api/v1/batch-optimization/tasks/{batch_id}/cancel",
        json={"cleanup_strategy": "rollback"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["rollback_performed"] is True
    for skill_id, (content, version) in skill_specs.items():
        assert skill_paths[skill_id].read_text(encoding="utf-8") == content
        storage.activate_version.assert_any_await(skill_id, version)
    assert storage.activate_version.await_count == 2
