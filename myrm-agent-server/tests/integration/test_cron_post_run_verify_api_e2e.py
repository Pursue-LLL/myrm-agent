"""Integration: Agent cron_post_run_verify CRUD + snapshot rollback via HTTP (no mocks on DB/AgentService)."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import patch

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config.settings import settings
from app.database.migrations import ensure_raw_sql_schema
from app.database.models import Base
from tests.support.minimal_app import build_minimal_app

API = f"{settings.api_prefix}/user-agents"


@pytest_asyncio.fixture()
async def _patched_db(tmp_path: Path):
    db_file = tmp_path / "cron_post_run_verify_integration.db"
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{db_file}",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await ensure_raw_sql_schema(engine)

    test_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    @asynccontextmanager
    async def mock_get_session():
        async with test_session() as session:
            try:
                yield session
            finally:
                await session.close()

    def mock_get_session_factory():
        return test_session

    with (
        patch("app.database.connection.get_session", mock_get_session),
        patch("app.platform_utils.get_session_factory", mock_get_session_factory),
        patch("app.database.repositories.uow.get_session_factory", mock_get_session_factory),
        patch("app.database.connection.get_session_factory", mock_get_session_factory),
        patch("app.services.budget.enforcer.get_session_factory", mock_get_session_factory),
    ):
        yield test_session

    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
    finally:
        await engine.dispose()


@pytest.fixture()
def client(_patched_db) -> TestClient:  # noqa: ANN001
    app = build_minimal_app("user_agents")
    with TestClient(app) as test_client:
        yield test_client


def _create_agent(client: TestClient, *, cron_post_run_verify: bool = False) -> str:
    resp = client.post(
        API,
        json={
            "name": "Delivery Verify Integration Agent",
            "system_prompt": "You are a test agent.",
            "cron_post_run_verify": cron_post_run_verify,
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]["id"]


def test_create_and_update_cron_post_run_verify_persists(client: TestClient) -> None:
    agent_id = _create_agent(client, cron_post_run_verify=False)

    get_resp = client.get(f"{API}/{agent_id}")
    assert get_resp.status_code == 200, get_resp.text
    assert get_resp.json()["data"]["cron_post_run_verify"] is False

    update_resp = client.put(
        f"{API}/{agent_id}",
        json={"cron_post_run_verify": True},
    )
    assert update_resp.status_code == 200, update_resp.text

    get_after = client.get(f"{API}/{agent_id}")
    assert get_after.status_code == 200, get_after.text
    assert get_after.json()["data"]["cron_post_run_verify"] is True


def test_snapshot_rollback_restores_cron_post_run_verify(client: TestClient) -> None:
    agent_id = _create_agent(client, cron_post_run_verify=False)

    client.put(f"{API}/{agent_id}", json={"cron_post_run_verify": True})
    assert client.get(f"{API}/{agent_id}").json()["data"]["cron_post_run_verify"] is True

    client.put(
        f"{API}/{agent_id}",
        json={"cron_post_run_verify": False, "system_prompt": "Mutated prompt."},
    )
    assert client.get(f"{API}/{agent_id}").json()["data"]["cron_post_run_verify"] is False

    rollback_resp = client.post(f"{API}/{agent_id}/rollback")
    assert rollback_resp.status_code == 200, rollback_resp.text

    after = client.get(f"{API}/{agent_id}")
    assert after.status_code == 200, after.text
    data = after.json()["data"]
    assert data["cron_post_run_verify"] is True
