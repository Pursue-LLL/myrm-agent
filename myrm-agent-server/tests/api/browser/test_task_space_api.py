"""Integration tests for Browser Task Spaces REST API endpoints."""

from __future__ import annotations

import pytest
from app.services.browser_spaces.task_space_service import (
    _reset_task_space_service_for_test,
    get_task_space_service,
)
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.browser_spaces import router as browser_spaces_router


@pytest.fixture
def client() -> TestClient:
    _reset_task_space_service_for_test()
    app = FastAPI()
    app.include_router(browser_spaces_router, prefix="/api/v1/browser")
    return TestClient(app)


def test_task_spaces_crud_lifecycle(client: TestClient) -> None:
    # 1. Initially empty
    res = client.get("/api/v1/browser/spaces")
    assert res.status_code == 200
    assert res.json() == []

    # 2. Create space A
    res = client.post(
        "/api/v1/browser/spaces",
        json={"space_id": "space-market-a", "name": "JD Price Tracker", "chat_id": "chat-123"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["space_id"] == "space-market-a"
    assert data["name"] == "JD Price Tracker"
    assert data["chat_id"] == "chat-123"
    assert data["status"] == "idle"
    assert data["takeover_active"] is False

    # 3. List should now have 1 space
    res = client.get("/api/v1/browser/spaces")
    assert res.status_code == 200
    assert len(res.json()) == 1

    # 4. Toggle takeover on
    res = client.post("/api/v1/browser/spaces/space-market-a/takeover", json={"enabled": True})
    assert res.status_code == 200
    assert res.json()["takeover_active"] is True
    assert res.json()["status"] == "takeover"

    # 5. Snapshot retrieval
    res = client.get("/api/v1/browser/spaces/space-market-a/snapshot")
    assert res.status_code == 200
    snap = res.json()
    assert snap["space_id"] == "space-market-a"
    assert snap["takeover_active"] is True

    # 6. Toggle takeover off
    res = client.post("/api/v1/browser/spaces/space-market-a/takeover", json={"enabled": False})
    assert res.status_code == 200
    assert res.json()["takeover_active"] is False
    assert res.json()["status"] == "idle"

    # 7. Prune idle spaces (none pruned if not expired)
    res = client.post("/api/v1/browser/spaces/prune?max_idle_seconds=100.0")
    assert res.status_code == 200
    assert res.json()["pruned_count"] == 0

    # 8. Close space
    res = client.delete("/api/v1/browser/spaces/space-market-a")
    assert res.status_code == 200
    assert res.json()["success"] is True

    # 9. Verify 404 on closed space
    res = client.delete("/api/v1/browser/spaces/space-market-a")
    assert res.status_code == 404


def test_task_spaces_quota_limit(client: TestClient) -> None:
    svc = get_task_space_service()
    svc.manager.max_active_spaces = 2

    # Create 2 spaces
    client.post("/api/v1/browser/spaces", json={"space_id": "sp-1"})
    client.post("/api/v1/browser/spaces", json={"space_id": "sp-2"})

    # 3rd should return 429
    res = client.post("/api/v1/browser/spaces", json={"space_id": "sp-3"})
    assert res.status_code == 429
    assert "Active BrowserTaskSpace limit reached" in res.json()["detail"]
