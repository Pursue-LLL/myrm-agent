"""Tests for compounding playbook status service and API."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from myrm_agent_harness.toolkits.cron.types import CronJob, JobStatus, JobType, Schedule, ScheduleKind, SessionTarget

from app.api.compounding_playbook.router import router
from app.api.cron.routes.helpers import _get_manager as get_cron_manager
from app.database.connection import get_db
from app.schemas.compounding_playbook import CompoundingChecklistItem, CompoundingPlaybookStatusResponse
from app.services.compounding_playbook.status_service import build_compounding_status
from app.services.memory.manager_deps import get_crud_memory_manager


def _sample_job(*, with_acceptance: bool) -> CronJob:
    return CronJob(
        id="job-1",
        user_id="default",
        name="Digest",
        job_type=JobType.AGENT,
        status=JobStatus.ACTIVE,
        schedule=Schedule(kind=ScheduleKind.CRON, expr="0 9 * * *", tz="UTC"),
        session_target=SessionTarget.ISOLATED,
        acceptance_criteria=({"type": "semantic", "description": "ok"},) if with_acceptance else (),
    )


@pytest.mark.asyncio
async def test_build_compounding_status_counts() -> None:
    memory_manager = MagicMock()
    memory_manager.count_memories = AsyncMock(side_effect=[2, 1, 0])

    cron_manager = MagicMock()
    cron_manager.list_jobs = AsyncMock(return_value=[_sample_job(with_acceptance=True)])

    snapshot = await build_compounding_status(
        memory_manager=memory_manager,
        cron_manager=cron_manager,
        agent_id=None,
        db=None,
    )

    assert snapshot.ready_count == 3
    assert snapshot.items[0].id == "memory"
    assert snapshot.items[0].count == 3
    assert snapshot.items[2].count == 1
    assert snapshot.items[3].count == 1
    assert snapshot.items[3].ready is True


def test_compounding_status_http_route() -> None:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_crud_memory_manager] = lambda: MagicMock()
    app.dependency_overrides[get_cron_manager] = lambda: MagicMock()
    app.dependency_overrides[get_db] = lambda: MagicMock()

    mock_response = CompoundingPlaybookStatusResponse(
        agent_id=None,
        items=[
            CompoundingChecklistItem(id="memory", ready=True, count=1, deep_link="/settings/memory"),
            CompoundingChecklistItem(id="skills", ready=False, count=0, deep_link="/settings/skills"),
            CompoundingChecklistItem(id="cron", ready=False, count=0, deep_link="/settings/cron"),
            CompoundingChecklistItem(id="verify", ready=False, count=0, deep_link="/settings/cron"),
        ],
        ready_count=1,
        total_count=4,
    )

    client = TestClient(app)
    with patch(
        "app.api.compounding_playbook.router.build_compounding_status",
        new_callable=AsyncMock,
        return_value=mock_response,
    ):
        response = client.get("/compounding-playbook/status")

    app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["ready_count"] == 1
    assert body["items"][0]["id"] == "memory"
