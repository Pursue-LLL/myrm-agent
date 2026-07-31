"""Integration: local-only media fixture seeds TaskStore for Chrome E2E."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from myrm_agent_harness.toolkits.tasks import SQLiteTaskStore

from app.api.tasks.deps import get_task_store
from app.api.tasks.router import router as tasks_router


def _build_tasks_app():
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(tasks_router, prefix="/api/v1/tasks")
    return app


@pytest.fixture
async def task_store(tmp_path: object) -> SQLiteTaskStore:
    db_path = tmp_path / "media-seed-fixture.db"  # type: ignore[operator]
    store = SQLiteTaskStore(db_path=str(db_path))
    await store.initialize()
    return store


@pytest.mark.integration
@pytest.mark.asyncio
async def test_seed_media_fixture_failed_mode_exposes_terminal_row(task_store: SQLiteTaskStore) -> None:
    app = _build_tasks_app()
    app.dependency_overrides[get_task_store] = lambda: task_store

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        seed_resp = await client.post("/api/v1/tasks/test/seed-media-fixture?mode=failed")
        assert seed_resp.status_code == 200
        seed = seed_resp.json()
        task_id = str(seed["task_id"])

        row_resp = await client.get(f"/api/v1/tasks/{task_id}")
        assert row_resp.status_code == 200
        row = row_resp.json()
        assert row["status"] == "failed"
        assert row["task_type"] == "image_generate"
        assert row["error"]["message"] == "MYRM_E2E_MEDIA_API_ERROR"

        list_resp = await client.get("/api/v1/tasks?status=failed&detail=true")
        assert list_resp.status_code == 200
        listed = list_resp.json()["tasks"]
        assert any(item["task_id"] == task_id for item in listed)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_seed_media_fixture_running_mode_exposes_active_row(task_store: SQLiteTaskStore) -> None:
    app = _build_tasks_app()
    app.dependency_overrides[get_task_store] = lambda: task_store

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        seed_resp = await client.post("/api/v1/tasks/test/seed-media-fixture?mode=running")
        assert seed_resp.status_code == 200
        seed = seed_resp.json()
        task_id = str(seed["task_id"])

        row_resp = await client.get(f"/api/v1/tasks/{task_id}")
        assert row_resp.status_code == 200
        row = row_resp.json()
        assert row["status"] == "running"
        assert row["progress"] == 0.42
