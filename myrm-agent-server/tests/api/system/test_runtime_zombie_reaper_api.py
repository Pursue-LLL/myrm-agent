"""
[INPUT]:
- httpx, ASGITransport
- app.api.system.runtime_zombie_reaper_api::router

[OUTPUT]:
- Pytest verification for causality graph snapshot, orphan reaper cascade kill, deadlock trip-wire, and failed task post-mortem REST endpoints.

[POS]:
tests/api/system/test_runtime_zombie_reaper_api.py — 智能体运行时因果拓扑与孤儿进程回收器 API 单元测试。
"""

from collections.abc import AsyncGenerator
from fastapi import FastAPI
import httpx
from httpx import ASGITransport
import pytest

from app.api.system.runtime_zombie_reaper_api import router as reaper_router

test_app = FastAPI()
test_app.include_router(reaper_router, prefix="/api/v1/system")


@pytest.fixture
async def async_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    async with httpx.AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://testserver",
        headers={"Content-Type": "application/json"},
    ) as client:
        yield client


@pytest.mark.asyncio
async def test_runtime_zombie_reaper_api_lifecycle(async_client: httpx.AsyncClient) -> None:
    # 1. Reset state
    reset_resp = await async_client.post("/api/v1/system/runtime-zombie-reaper/reset")
    assert reset_resp.status_code == 200
    assert reset_resp.json() == {"status": "reset"}

    # 2. Register parent agent node
    parent_resp = await async_client.post(
        "/api/v1/system/runtime-zombie-reaper/register-node",
        json={
            "node_id": "agent-root",
            "name": "Primary Orchestrator",
            "role": "primary_agent",
            "pid": 5001,
            "pgid": 5000,
            "profile_id": "orchestrator-profile",
            "state": "running",
            "cpu_percent": 12.5,
            "memory_rss_mb": 128.0,
            "tokens_consumed": 1500,
        },
    )
    assert parent_resp.status_code == 200
    assert parent_resp.json() == {"status": "upserted", "node_id": "agent-root"}

    # 3. Register child subagent node
    child_resp = await async_client.post(
        "/api/v1/system/runtime-zombie-reaper/register-node",
        json={
            "node_id": "subagent-worker",
            "name": "Code Executor Subagent",
            "role": "subagent",
            "pid": 5002,
            "pgid": 5000,
            "parent_id": "agent-root",
            "profile_id": "sandbox-executor",
            "state": "running",
            "cpu_percent": 45.0,
            "memory_rss_mb": 256.0,
            "tokens_consumed": 3200,
        },
    )
    assert child_resp.status_code == 200

    # 4. Snapshot check
    snap_resp = await async_client.get("/api/v1/system/runtime-zombie-reaper/snapshot")
    assert snap_resp.status_code == 200
    snap_data = snap_resp.json()
    node_ids = [n["node_id"] for n in snap_data["nodes"]]
    assert len(snap_data["nodes"]) == 2
    assert "agent-root" in node_ids
    assert "subagent-worker" in node_ids
    assert len(snap_data["profile_summaries"]) >= 2

    # 5. Deadlock check while running -> Should be False
    deadlock_resp = await async_client.get(
        "/api/v1/system/runtime-zombie-reaper/check-deadlock",
        params={"parent_id": "agent-root", "child_id": "subagent-worker"},
    )
    assert deadlock_resp.status_code == 200
    deadlock_data = deadlock_resp.json()
    assert deadlock_data["is_deadlocked"] is False
    assert deadlock_data["fault_message"] is None

    # 6. Simulate subagent crash
    crash_resp = await async_client.post(
        "/api/v1/system/runtime-zombie-reaper/register-node",
        json={
            "node_id": "subagent-worker",
            "name": "Code Executor Subagent",
            "role": "subagent",
            "pid": 5002,
            "pgid": 5000,
            "parent_id": "agent-root",
            "profile_id": "sandbox-executor",
            "state": "crashed",
            "exit_code": 137,
            "crash_reason": "SIGKILL OOM 内存耗尽",
        },
    )
    assert crash_resp.status_code == 200

    # 7. Deadlock check after crash -> Should trigger trip-wire
    deadlock_tripped = await async_client.get(
        "/api/v1/system/runtime-zombie-reaper/check-deadlock",
        params={"parent_id": "agent-root", "child_id": "subagent-worker"},
    )
    assert deadlock_tripped.status_code == 200
    assert deadlock_tripped.json()["is_deadlocked"] is True
    assert "SIGKILL OOM" in (deadlock_tripped.json()["fault_message"] or "")

    # 8. Record failed task entry
    fail_task_resp = await async_client.post(
        "/api/v1/system/runtime-zombie-reaper/record-failed-task",
        json={
            "task_id": "task-err-999",
            "name": "Distributed Compilation",
            "parent_task_id": "agent-root",
            "profile_id": "sandbox-executor",
            "exit_code": 137,
            "crash_reason": "SIGKILL OOM 内存耗尽",
            "duration_ms": 4200,
        },
    )
    assert fail_task_resp.status_code == 200
    assert fail_task_resp.json()["task_id"] == "task-err-999"

    # 9. Register an auxiliary helper under subagent
    await async_client.post(
        "/api/v1/system/runtime-zombie-reaper/register-node",
        json={
            "node_id": "helper-proc-1",
            "name": "Compiler daemon",
            "role": "helper_process",
            "pid": 5003,
            "pgid": 5000,
            "parent_id": "agent-root",
            "state": "running",
        },
    )

    # 10. Reap orphans for parent-root
    reap_resp = await async_client.post(
        "/api/v1/system/runtime-zombie-reaper/reap-orphans",
        json={"parent_id": "agent-root", "reason": "Parent session closed"},
    )
    assert reap_resp.status_code == 200
    reap_data = reap_resp.json()
    assert reap_data["reaped_count"] >= 1
    assert "helper-proc-1" in reap_data["reaped_node_ids"]
