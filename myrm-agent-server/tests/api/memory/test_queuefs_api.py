"""[POS]: tests/api/memory/test_queuefs_api.py
[INPUT]: FastAPI TestClient and memory QueueFS endpoints.
[OUTPUT]: Pytest integration tests verifying async DAG scheduling and hierarchical path semantic locking.
"""

from collections.abc import AsyncGenerator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from myrm_agent_harness.toolkits.memory import (
    PathSemanticLockManager,
    QueueFSConfig,
    QueueFSDAGEngine,
)

from app.api.memory.queuefs_router import (
    router as queuefs_router,
)
from app.services.memory.queuefs_service import (
    QueueFSService,
    get_queuefs_service,
)


@pytest.fixture
def app() -> FastAPI:
    """Create isolated FastAPI instance mounting queuefs router with clean engines."""
    test_app = FastAPI()
    test_app.include_router(queuefs_router)
    clean_lock = PathSemanticLockManager(default_ttl_seconds=5.0)
    clean_engine = QueueFSDAGEngine(
        config=QueueFSConfig(lock_ttl_seconds=5.0),
        lock_manager=clean_lock,
    )
    clean_service = QueueFSService(
        dag_engine=clean_engine,
        lock_manager=clean_lock,
    )
    test_app.dependency_overrides[get_queuefs_service] = lambda: clean_service
    return test_app


@pytest.fixture
async def client(app: FastAPI) -> AsyncGenerator[AsyncClient, None]:
    """Create async HTTP client for FastAPI test app."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac


@pytest.mark.anyio
async def test_queuefs_task_lifecycle_api(client: AsyncClient) -> None:
    """Verify task submission, advance, execute pipeline, and stats query."""
    # 1. Submit task
    submit_payload = {
        "resource_uri": "context://resources/handbook.md",
        "payload": "# Operations Guide\nStep 1...",
    }
    submit_resp = await client.post("/queuefs/tasks/submit", json=submit_payload)
    assert submit_resp.status_code == 202
    task = submit_resp.json()
    task_id = task["task_id"]
    assert task_id.startswith("qfs_task_")
    assert task["resource_uri"] == "context://resources/handbook.md"
    assert task["status"] == "pending"
    assert task["current_stage"] == "ingestion"

    # 2. Get task
    get_resp = await client.get(f"/queuefs/tasks/{task_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["task_id"] == task_id

    # 3. Advance single stage
    adv_resp = await client.post(f"/queuefs/tasks/{task_id}/advance")
    assert adv_resp.status_code == 200
    adv_data = adv_resp.json()
    assert adv_data["status"] == "running"
    assert adv_data["current_stage"] == "chunking"

    # 4. Execute remainder of pipeline
    exec_resp = await client.post(f"/queuefs/tasks/{task_id}/execute")
    assert exec_resp.status_code == 200
    exec_data = exec_resp.json()
    assert exec_data["status"] == "completed"
    assert exec_data["progress_pct"] == 100.0

    # 5. List tasks
    list_resp = await client.get("/queuefs/tasks?status=completed")
    assert list_resp.status_code == 200
    tasks_list = list_resp.json()
    assert len(tasks_list) >= 1
    assert any(t["task_id"] == task_id for t in tasks_list)

    # 6. Check stats
    stats_resp = await client.get("/queuefs/stats")
    assert stats_resp.status_code == 200
    stats = stats_resp.json()
    assert stats["completed_tasks"] >= 1


@pytest.mark.anyio
async def test_queuefs_task_not_found(client: AsyncClient) -> None:
    """Verify 404 returned for unknown task IDs."""
    get_resp = await client.get("/queuefs/tasks/non_existent_id")
    assert get_resp.status_code == 404

    adv_resp = await client.post("/queuefs/tasks/non_existent_id/advance")
    assert adv_resp.status_code == 404

    exec_resp = await client.post("/queuefs/tasks/non_existent_id/execute")
    assert exec_resp.status_code == 404


@pytest.mark.anyio
async def test_path_semantic_lock_flow(client: AsyncClient) -> None:
    """Verify hierarchical path lock acquisition, conflict detection (409), and release."""
    # 1. Acquire exclusive lock on pattern
    acq_payload = {
        "path_pattern": "context://resources/docs/*",
        "owner": "worker-1",
        "mode": "exclusive",
        "ttl_seconds": 10.0,
    }
    acq_resp = await client.post("/queuefs/locks/acquire", json=acq_payload)
    assert acq_resp.status_code == 200
    acq_data = acq_resp.json()
    lock_id = acq_data["lock_id"]
    assert acq_data["mode"] == "exclusive"
    assert acq_data["owner"] == "worker-1"

    # 2. Check lock status
    check_resp = await client.get("/queuefs/locks/check?path=context://resources/docs/guide.md")
    assert check_resp.status_code == 200
    check_data = check_resp.json()
    assert check_data["is_locked"] is True
    assert check_data["active_locks_count"] == 1

    # 3. Conflicting acquisition by another worker yields 409
    conflict_payload = {
        "path_pattern": "context://resources/docs/guide.md",
        "owner": "worker-2",
        "mode": "exclusive",
    }
    conflict_resp = await client.post("/queuefs/locks/acquire", json=conflict_payload)
    assert conflict_resp.status_code == 409
    assert "conflicts with active lease" in conflict_resp.json()["detail"]

    # 4. Release lock
    rel_resp = await client.post("/queuefs/locks/release", json={"lock_id": lock_id, "owner": "worker-1"})
    assert rel_resp.status_code == 200
    assert rel_resp.json()["released"] is True

    # 5. Check post-release status
    post_check = await client.get("/queuefs/locks/check?path=context://resources/docs/guide.md")
    assert post_check.status_code == 200
    assert post_check.json()["is_locked"] is False
    assert post_check.json()["active_locks_count"] == 0
