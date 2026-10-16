"""HTTP integration: POST /skill-optimization/mutations/{batch_id}/rollback."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api.skill_optimization.routes import versions as versions_routes
from app.database.connection import get_db
from app.database.models import Base
from app.services.skill_optimization.rollback_service import RollbackService
from app.services.skills.mutation_batch_service import MutationBatchCompensationError, MutationBatchRollbackError


@pytest.fixture
def rollback_http_client() -> Iterator[tuple[TestClient, async_sessionmaker[AsyncSession]]]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    async def init_db() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(init_db())
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def override_get_db() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app = FastAPI()
    app.include_router(versions_routes.router, prefix="/api/v1/skill-optimization")
    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as client:
        yield client, session_factory

    asyncio.run(engine.dispose())


async def _seed_snapshot(session_factory: async_sessionmaker[AsyncSession], batch_id: str) -> None:
    async with session_factory() as session:
        service = RollbackService(session)
        await service.insert_mutation_batch_snapshot(
            batch_id=batch_id,
            skill_id="skill-1",
            skill_content="before-md",
            metadata={
                "batch_kind": "skill_mutation",
                "resource_files": {},
                "existed_before_batch": True,
            },
        )
        await session.commit()


def test_mutation_batch_rollback_route_success(
    rollback_http_client: tuple[TestClient, async_sessionmaker[AsyncSession]],
) -> None:
    client, session_factory = rollback_http_client
    batch_id = "batch-http-1"
    asyncio.run(_seed_snapshot(session_factory, batch_id))

    live_state = type(
        "Live",
        (),
        {
            "skill_id": "skill-1",
            "skill_md": "live-md",
            "resources": {},
            "skill_existed": True,
        },
    )()

    with (
        patch(
            "app.services.skills.mutation_batch_service._capture_live_state",
            AsyncMock(return_value=live_state),
        ),
        patch(
            "app.services.skills.write_orchestrator.orchestrate_skill_file_write",
            AsyncMock(),
        ),
        patch("app.core.skills.config_version.bump_skill_config_version"),
    ):
        response = client.post(f"/api/v1/skill-optimization/mutations/{batch_id}/rollback")

    assert response.status_code == 200
    body = response.json()
    assert body["batch_id"] == batch_id
    assert body["skills_restored"] == 1


def test_mutation_batch_rollback_route_already_consumed(
    rollback_http_client: tuple[TestClient, async_sessionmaker[AsyncSession]],
) -> None:
    client, _session_factory = rollback_http_client
    response = client.post("/api/v1/skill-optimization/mutations/missing-batch/rollback")
    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["code"] == "batch_already_consumed"


@pytest.mark.parametrize(
    ("failure", "expected_code"),
    [
        (MutationBatchCompensationError("restoring the live state failed"), "compensation_failed"),
        (MutationBatchRollbackError("snapshot is not rollback-eligible"), "rollback_failed"),
    ],
)
def test_mutation_batch_rollback_route_maps_failures_to_the_codes_the_frontend_reads(
    rollback_http_client: tuple[TestClient, async_sessionmaker[AsyncSession]],
    failure: MutationBatchRollbackError,
    expected_code: str,
) -> None:
    """The undo action picks its toast from ``detail.code``; a renamed code would silently fall back to the generic one."""
    client, _session_factory = rollback_http_client
    with patch(
        "app.services.skills.mutation_batch_service.rollback_skill_mutation_batch",
        AsyncMock(side_effect=failure),
    ):
        response = client.post("/api/v1/skill-optimization/mutations/batch-failing/rollback")

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["code"] == expected_code
    assert detail["message"] == str(failure)
