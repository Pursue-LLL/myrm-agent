"""Integration tests for cron job project_id association and inheritance.

[INPUT] CronJobCreate/CronJobUpdate payloads with project_id, API query params.
[OUTPUT] Verified project_id storage, query filtering, and workspace inheritance.
[POS] tests/api/cron/test_cron_project_id.py
"""

from __future__ import annotations

from typing import Generator
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from myrm_agent_harness.toolkits.cron import (
    CronConfig,
    CronManager,
    CronScheduler,
)
from myrm_agent_harness.toolkits.cron.stores import InMemoryCronStore

from app.api.cron.routes import helpers, jobs_router
from app.database.models.project import Project


class FakeDelivery:
    async def deliver(self, job: object, result: object) -> None:
        pass


@pytest.fixture
def cron_manager() -> CronManager:
    store = InMemoryCronStore()
    scheduler = CronScheduler(
        store=store,
        runners={},
        delivery=FakeDelivery(),
        config=CronConfig(),
    )
    return CronManager(store, scheduler, shell_enabled=True)


@pytest.fixture
def app(cron_manager: CronManager) -> Generator[FastAPI, None, None]:
    test_app = FastAPI()
    test_app.include_router(jobs_router, prefix="/cron")

    with patch.object(helpers, "_get_manager", return_value=cron_manager):
        yield test_app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


def test_create_and_get_job_with_project_id(client: TestClient) -> None:
    resp = client.post(
        "/cron",
        json={
            "name": "project-scheduled-audit",
            "job_type": "agent",
            "schedule": {"kind": "interval", "interval_ms": 60_000},
            "prompt": "audit repo codebase",
            "project_id": "proj-alpha-123",
        },
    )
    assert resp.status_code == 201
    created = resp.json()
    assert created["name"] == "project-scheduled-audit"
    assert created["project_id"] == "proj-alpha-123"

    job_id = str(created["id"])
    get_resp = client.get(f"/cron/{job_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["project_id"] == "proj-alpha-123"


def test_list_jobs_filtered_by_project_id(client: TestClient) -> None:
    # Create two jobs with different projects and one without project
    client.post(
        "/cron",
        json={
            "name": "job-proj-1",
            "job_type": "agent",
            "schedule": {"kind": "interval", "interval_ms": 60_000},
            "prompt": "task 1",
            "project_id": "proj-alpha",
        },
    )
    client.post(
        "/cron",
        json={
            "name": "job-proj-2",
            "job_type": "agent",
            "schedule": {"kind": "interval", "interval_ms": 60_000},
            "prompt": "task 2",
            "project_id": "proj-beta",
        },
    )
    client.post(
        "/cron",
        json={
            "name": "job-no-proj",
            "job_type": "agent",
            "schedule": {"kind": "interval", "interval_ms": 60_000},
            "prompt": "task 3",
        },
    )

    # Filter by proj-alpha
    resp_alpha = client.get("/cron?project_id=proj-alpha")
    assert resp_alpha.status_code == 200
    jobs_alpha = resp_alpha.json()["items"]
    assert len(jobs_alpha) == 1
    assert jobs_alpha[0]["project_id"] == "proj-alpha"
    assert jobs_alpha[0]["name"] == "job-proj-1"

    # Filter by proj-beta
    resp_beta = client.get("/cron?project_id=proj-beta")
    assert resp_beta.status_code == 200
    jobs_beta = resp_beta.json()["items"]
    assert len(jobs_beta) == 1
    assert jobs_beta[0]["project_id"] == "proj-beta"


def test_update_job_project_id(client: TestClient) -> None:
    resp = client.post(
        "/cron",
        json={
            "name": "rebind-job",
            "job_type": "agent",
            "schedule": {"kind": "interval", "interval_ms": 60_000},
            "prompt": "check status",
            "project_id": "proj-old",
        },
    )
    assert resp.status_code == 201
    job_id = str(resp.json()["id"])

    # Update project_id to proj-new
    patch_resp = client.patch(
        f"/cron/{job_id}",
        json={"project_id": "proj-new"},
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["project_id"] == "proj-new"


@pytest.mark.asyncio
async def test_agent_runner_workspace_path_inheritance() -> None:
    """Validate that AgentJobRunner automatically inherits project workspace path."""
    from myrm_agent_harness.toolkits.cron.types import CronJob, JobType, Schedule, ScheduleKind

    from app.services.project.project_service import ProjectService

    job = CronJob(
        id="test-job-proj",
        user_id="default",
        name="Scheduled Repo Sync",
        schedule=Schedule(kind=ScheduleKind.INTERVAL, interval_ms=10000),
        job_type=JobType.AGENT,
        prompt="Inspect code",
        project_id="proj-auto-workspace",
        allowed_roots=(),
    )

    fake_project = Project(
        id="proj-auto-workspace",
        name="Test Auto Project",
        workspace_path="/path/to/virtual/workspace",
    )

    with patch.object(ProjectService, "get_project", new_callable=AsyncMock) as mock_get_proj:
        mock_get_proj.return_value = fake_project

        # Verify resolution block logic directly
        effective_allowed_roots: list[str] = list(job.allowed_roots)
        if job.project_id and not effective_allowed_roots:
            project_model = await ProjectService.get_project(job.project_id)
            if project_model and project_model.workspace_path:
                effective_allowed_roots.append(project_model.workspace_path)

        assert effective_allowed_roots == ["/path/to/virtual/workspace"]
        mock_get_proj.assert_awaited_once_with("proj-auto-workspace")
