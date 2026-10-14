"""Unit tests for Ebbinghaus memory decay and tiered storage lifecycle REST APIs.

[INPUT]
- TestClient plus memories seeded directly into the lifecycle manager.

[OUTPUT]
- Pytest cases validating /api/memory/lifecycle/ endpoints.

[POS]
- tests.api.memory.test_decay_lifecycle_api
"""

import time

import pytest
from fastapi import FastAPI
from myrm_agent_harness.toolkits.memory.decay import TieredStorageLifecycleManager
from starlette.testclient import TestClient

from app.api.memory.decay_lifecycle_router import (
    router as decay_lifecycle_router,
)
from app.services.memory.decay_lifecycle_service import decay_lifecycle_service


@pytest.fixture
def lifecycle_manager(monkeypatch: pytest.MonkeyPatch) -> TieredStorageLifecycleManager:
    """Swap the service's lifecycle manager for an empty one so each test seeds its own memories."""
    manager = TieredStorageLifecycleManager(scorer=decay_lifecycle_service.scorer)
    monkeypatch.setattr(decay_lifecycle_service, "lifecycle_manager", manager)
    return manager


@pytest.fixture
def client(lifecycle_manager: TieredStorageLifecycleManager) -> TestClient:
    """Provide isolated TestClient fixture mounting decay lifecycle router."""
    test_app = FastAPI()
    test_app.include_router(decay_lifecycle_router, prefix="/api/memory")
    with TestClient(test_app) as test_client:
        yield test_client


def test_evaluate_lifecycle_api(client: TestClient, lifecycle_manager: TieredStorageLifecycleManager) -> None:
    """Verify POST /evaluate re-tiers tracked memories by age and importance."""
    t0 = time.time()
    lifecycle_manager.register_memory(
        memory_id="mem-api-active",
        content="User prefers concise answers",
        importance=0.9,
        pinned=True,
        created_at=t0,
    )
    lifecycle_manager.register_memory(
        memory_id="mem-api-stale",
        content="Temporary test token",
        importance=0.3,
        pinned=False,
        created_at=t0 - 60 * 86400.0,
    )

    eval_resp = client.post(
        "/api/memory/lifecycle/evaluate",
        json={"current_time": t0},
    )
    assert eval_resp.status_code == 200
    eval_data = eval_resp.json()
    assert eval_data["total_evaluated"] == 2
    assert eval_data["hot_count"] >= 1


def test_revive_and_export_cold_archive_api(client: TestClient, lifecycle_manager: TieredStorageLifecycleManager) -> None:
    """Verify GET /cold-archive and POST /revive endpoints."""
    t0 = time.time()

    # Track a memory and evaluate it into the cold tier
    lifecycle_manager.register_memory(
        memory_id="mem-to-archive",
        content="Old archive item",
        importance=0.2,
        created_at=t0 - 80 * 86400.0,
    )
    client.post("/api/memory/lifecycle/evaluate", json={"current_time": t0})

    # Export cold archive
    archive_resp = client.get("/api/memory/lifecycle/cold-archive")
    assert archive_resp.status_code == 200
    archive_data = archive_resp.json()
    assert archive_data["total_archived"] >= 1
    assert any(r["memory_id"] == "mem-to-archive" for r in archive_data["records"])

    # Revive cold memory
    revive_resp = client.post(
        "/api/memory/lifecycle/revive",
        json={"memory_id": "mem-to-archive", "boost_importance": 0.95},
    )
    assert revive_resp.status_code == 200
    revive_data = revive_resp.json()
    assert revive_data["memory_id"] == "mem-to-archive"
    assert revive_data["new_tier"] == "HOT"
