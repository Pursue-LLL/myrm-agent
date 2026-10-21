"""API integration tests for High-Concurrency Swarm & Adaptive Cloud Offload (Item 60).

[INPUT]
- app.api.agents.swarm_offload_router.router
- app.services.agent.swarm_offload_service.get_swarm_offload_service

[OUTPUT]
- Pytest test cases validating 10-15 subagent swarm batch dispatch,
  host resource watermark telemetry, adaptive offload routing, and policy updates.

[POS]
- myrm-agent/myrm-agent-server/tests/api/agents/test_swarm_offload_api.py
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api.agents.swarm_offload_router import router as swarm_offload_router
from app.services.agent.swarm_offload_service import (
    SwarmOffloadService,
    get_swarm_offload_service,
)


@pytest.fixture
def service() -> SwarmOffloadService:
    """Isolated SwarmOffloadService fixture for test execution."""
    srv = SwarmOffloadService()
    srv.clear()
    return srv


@pytest.fixture
def client(service: SwarmOffloadService) -> Generator[TestClient, None, None]:
    """TestClient fixture with injected SwarmOffloadService dependency."""
    app = FastAPI()
    app.include_router(swarm_offload_router)
    app.dependency_overrides[get_swarm_offload_service] = lambda: service
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_get_and_report_resource_watermark_api(client: TestClient) -> None:
    """Test reading host watermark and reporting updated CPU/memory telemetry."""
    # 1. Initial watermark reading
    resp = client.get("/agents/swarm-offload/watermark")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "cpu_percent" in data
    assert "memory_percent" in data
    assert "is_over_watermark" in data
    assert not data["is_over_watermark"]
    assert data["recommendation"] == "local_host"

    # 2. Report high CPU load from desktop probe
    report_payload = {"cpu_percent": 92.5, "memory_percent": 86.0}
    report_resp = client.post("/agents/swarm-offload/watermark/report", json=report_payload)
    assert report_resp.status_code == 200
    rep_data = report_resp.json()["data"]
    assert rep_data["cpu_percent"] == 92.5
    assert rep_data["memory_percent"] == 86.0
    assert rep_data["is_over_watermark"]
    assert rep_data["recommendation"] == "cloud_sandbox"


def test_dispatch_swarm_batch_and_get_batch_api(client: TestClient) -> None:
    """Test dispatching 12 concurrent subagents and fetching batch summary."""
    batch_id = "batch-test-swarm-12"
    tasks = [
        {
            "task_id": f"task-sw-{i:02d}",
            "title": f"Parallel Spec Validation #{i}",
            "command_or_prompt": f"pytest tests/unit/test_module_{i}.py",
            "priority": "normal",
            "timeout_seconds": 15.0,
        }
        for i in range(12)
    ]
    dispatch_payload = {
        "batch_id": batch_id,
        "tasks": tasks,
    }

    resp = client.post("/agents/swarm-offload/dispatch", json=dispatch_payload)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["batch_id"] == batch_id
    assert data["total_tasks"] == 12
    assert data["completed_count"] == 12
    assert data["failed_count"] == 0
    assert len(data["workers"]) == 12
    assert data["local_workers_count"] + data["cloud_workers_count"] == 12

    # Query batch details by ID
    get_resp = client.get(f"/agents/swarm-offload/batches/{batch_id}")
    assert get_resp.status_code == 200
    get_data = get_resp.json()["data"]
    assert get_data["batch_id"] == batch_id
    assert get_data["total_tasks"] == 12

    # Query nonexistent batch returns 404
    missing_resp = client.get("/agents/swarm-offload/batches/nonexistent-batch-999")
    assert missing_resp.status_code == 404


def test_update_offload_policy_api(client: TestClient) -> None:
    """Test switching offloading policy to FORCE_CLOUD and verifying execution behavior."""
    # 1. Update policy
    policy_resp = client.post("/agents/swarm-offload/policy", json={"strategy": "force_cloud"})
    assert policy_resp.status_code == 200
    assert policy_resp.json()["data"]["strategy"] == "force_cloud"

    # 2. Dispatch tasks under force_cloud
    tasks = [
        {
            "task_id": f"cloud-t-{i}",
            "title": f"Cloud Task #{i}",
            "command_or_prompt": f"echo cloud task {i}",
        }
        for i in range(3)
    ]
    dispatch_resp = client.post("/agents/swarm-offload/dispatch", json={"tasks": tasks})
    assert dispatch_resp.status_code == 200
    data = dispatch_resp.json()["data"]
    assert data["total_tasks"] == 3
    assert data["cloud_workers_count"] == 3
    assert data["local_workers_count"] == 0


def test_dispatch_batch_validation_error(client: TestClient) -> None:
    """Test that dispatching empty tasks list triggers 422 validation failure."""
    resp = client.post("/agents/swarm-offload/dispatch", json={"tasks": []})
    assert resp.status_code == 422
