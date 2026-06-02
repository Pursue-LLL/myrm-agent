from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.database.connection import get_db

batch_router_module = importlib.import_module("app.api.batch_optimization.router")


@dataclass(slots=True)
class FakeBatchTask:
    batch_id: str
    max_concurrent: int
    status: str = "running"
    priority: int = 1
    skill_ids: dict[str, list[str]] = field(default_factory=lambda: {"ids": ["skill-a"]})
    total_tasks: int = 1
    completed_tasks: int = 1
    failed_tasks: int = 0
    cancelled_tasks: int = 0
    total_execution_time: float = 12.5
    total_token_consumption: int = 2400
    estimated_completion_time: datetime | None = None
    created_at: datetime = datetime(2026, 4, 14, 15, 5, 40, tzinfo=timezone.utc)
    started_at: datetime | None = datetime(2026, 4, 14, 15, 6, 0, tzinfo=timezone.utc)
    completed_at: datetime | None = None
    error_message: str | None = None
    user_id: str | None = "test-user-id"


class BatchTaskRepositoryStub:
    def __init__(self, session: object, task: FakeBatchTask) -> None:
        self.session = session
        self.task = task

    async def get_by_user(self, user_id: str, limit: int) -> list[FakeBatchTask]:
        return [self.task]

    async def get_by_id(self, batch_id: str) -> FakeBatchTask | None:
        return self.task if batch_id == self.task.batch_id else None


class AuditLogRepositoryStub:
    def __init__(self, session: object) -> None:
        self.session = session

    async def get_batch_logs(self, batch_id: str) -> list[object]:
        return []


@pytest.fixture
def app() -> FastAPI:
    app = FastAPI()
    app.include_router(batch_router_module.router, prefix="/api/v1")

    async def mock_get_deploy_identity() -> str:
        return "test-user-id"

    async def mock_get_db():
        yield AsyncMock()

    pass
    app.dependency_overrides[get_db] = mock_get_db
    return app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


def test_batch_tasks_list_includes_max_concurrent(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task = FakeBatchTask(batch_id="batch-123", max_concurrent=7)
    monkeypatch.setattr(
        batch_router_module,
        "BatchTaskRepository",
        lambda session: BatchTaskRepositoryStub(session, task),
    )

    response = client.get("/api/v1/batch-optimization/tasks")

    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    assert body["tasks"][0]["batch_id"] == "batch-123"
    assert body["tasks"][0]["max_concurrent"] == 7


def test_batch_task_detail_includes_max_concurrent(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task = FakeBatchTask(batch_id="batch-456", max_concurrent=5)
    monkeypatch.setattr(
        batch_router_module,
        "BatchTaskRepository",
        lambda session: BatchTaskRepositoryStub(session, task),
    )
    monkeypatch.setattr(
        batch_router_module,
        "AuditLogRepository",
        lambda session: AuditLogRepositoryStub(session),
    )

    response = client.get("/api/v1/batch-optimization/tasks/batch-456")

    assert response.status_code == 200
    body = response.json()
    assert body["batch_id"] == "batch-456"
    assert body["max_concurrent"] == 5
    assert body["audit_logs"] == []
