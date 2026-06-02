"""End-to-end integration test: cron job ↔ agent binding.

Uses real in-memory SQLite (no mocks for DB) + real Cron Manager + real Agent CRUD.
Validates the full flow:
  create agent → create cron job with agent_id → query → update → verify.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from myrm_agent_harness.toolkits.cron import CronConfig, CronManager, CronScheduler
from myrm_agent_harness.toolkits.cron.stores import InMemoryCronStore
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.database.models import Base

TEST_USER = "integration-test-user"


class _NoopDelivery:
    async def deliver(self, job, result):  # noqa: ANN001
        pass


@pytest.fixture()
async def _db_engine():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture()
def app(_db_engine) -> FastAPI:  # noqa: ANN001
    """Build a minimal FastAPI app with real DB session and both agent + cron routers."""
    from unittest.mock import patch

    TestSessionLocal = sessionmaker(_db_engine, class_=AsyncSession, expire_on_commit=False)

    @asynccontextmanager
    async def _real_session() -> AsyncGenerator[AsyncSession, None]:
        async with TestSessionLocal() as session:
            try:
                yield session
            finally:
                await session.close()

    store = InMemoryCronStore()
    scheduler = CronScheduler(store=store, runners={}, delivery=_NoopDelivery(), config=CronConfig())
    manager = CronManager(store, scheduler, shell_enabled=False)

    test_app = FastAPI()

    async def mock_user_id() -> str:
        return TEST_USER

    from app.api.agents.agent import router as agent_router
    from app.api.cron.routes import router as cron_router
    from app.api.dependencies import get_db

    pass
    test_app.dependency_overrides[get_db] = _real_session

    test_app.include_router(agent_router, prefix="/api/agents")
    test_app.include_router(cron_router, prefix="/cron")

    with (
        patch("app.api.cron.routes.helpers._get_manager", return_value=manager),
        patch("app.platform_utils.get_session_factory", return_value=TestSessionLocal),
        patch("app.database.connection.get_session_factory", return_value=TestSessionLocal),
        patch("app.database.repositories.uow.get_session_factory", return_value=TestSessionLocal),
    ):
        yield test_app


@pytest.fixture()
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


def _create_agent(client: TestClient, name: str = "Test Agent") -> str:
    resp = client.post(
        "/api/agents",
        json={"name": name, "system_prompt": "You are a test agent."},
    )
    assert resp.status_code == 200
    data = resp.json()
    return data["data"]["id"]


def _create_cron_job(
    client: TestClient,
    name: str = "test-job",
    agent_id: str | None = None,
) -> dict[str, object]:
    body: dict[str, object] = {
        "name": name,
        "job_type": "agent",
        "schedule": {"kind": "interval", "interval_ms": 300_000},
        "prompt": "check status",
    }
    if agent_id is not None:
        body["agent_id"] = agent_id
    resp = client.post("/cron", json=body)
    assert resp.status_code == 201
    return resp.json()


@pytest.mark.integration
@pytest.mark.skip(reason="Cron job CRUD endpoints removed from routes/jobs.py; binding tests require API rebuild")
class TestCronAgentBindingE2E:
    """Full agent binding lifecycle via real API."""

    def test_create_job_with_agent_binding(self, client: TestClient) -> None:
        agent_id = _create_agent(client, "Cron Agent")
        job = _create_cron_job(client, "bound-task", agent_id=agent_id)

        assert job["agent_id"] == agent_id

        resp = client.get(f"/cron/{job['id']}")
        assert resp.status_code == 200
        assert resp.json()["agent_id"] == agent_id

    def test_create_job_without_agent(self, client: TestClient) -> None:
        job = _create_cron_job(client, "no-agent-task")
        assert job["agent_id"] is None

    def test_bind_agent_via_update(self, client: TestClient) -> None:
        agent_id = _create_agent(client, "Late Bind Agent")
        job = _create_cron_job(client, "late-bind-task")
        assert job["agent_id"] is None

        resp = client.patch(f"/cron/{job['id']}", json={"agent_id": agent_id})
        assert resp.status_code == 200
        assert resp.json()["agent_id"] == agent_id

    def test_rebind_to_different_agent(self, client: TestClient) -> None:
        agent_a = _create_agent(client, "Agent A")
        agent_b = _create_agent(client, "Agent B")
        job = _create_cron_job(client, "rebind-task", agent_id=agent_a)

        resp = client.patch(f"/cron/{job['id']}", json={"agent_id": agent_b})
        assert resp.status_code == 200
        assert resp.json()["agent_id"] == agent_b

    def test_agent_id_survives_pause_resume(self, client: TestClient) -> None:
        agent_id = _create_agent(client, "Persistent Agent")
        job = _create_cron_job(client, "survive-task", agent_id=agent_id)

        client.post(f"/cron/{job['id']}/pause")
        resp = client.post(f"/cron/{job['id']}/resume")
        assert resp.status_code == 200
        assert resp.json()["agent_id"] == agent_id

    def test_list_shows_agent_id(self, client: TestClient) -> None:
        agent_id = _create_agent(client, "List Agent")
        _create_cron_job(client, "listed-task", agent_id=agent_id)

        resp = client.get("/cron")
        assert resp.status_code == 200
        items = resp.json()["items"]
        bound_jobs = [j for j in items if j["agent_id"] == agent_id]
        assert len(bound_jobs) == 1

    def test_delete_job_with_agent(self, client: TestClient) -> None:
        agent_id = _create_agent(client, "Delete Agent")
        job = _create_cron_job(client, "delete-task", agent_id=agent_id)

        resp = client.delete(f"/cron/{job['id']}")
        assert resp.status_code == 204

        resp = client.get(f"/cron/{job['id']}")
        assert resp.status_code == 404
