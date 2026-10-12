"""Integration and unit tests for Task HUD & Anti-Compaction Task State API endpoints.

[INPUT]
- httpx, ASGITransport
- app.api.chats.chat.task_hud::router

[OUTPUT]
- Pytest test cases verifying task isolation, HUD text injection, and task mutations.

[POS]
Server-side integration test suite for Item 31. Strictly under 180 lines. Zero `Any`.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator

import httpx
import pytest
from fastapi import FastAPI
from httpx import ASGITransport

from app.api.chats.chat.task_hud import router as task_hud_router

# Build isolated minimal test application
test_app = FastAPI()
test_app.include_router(task_hud_router, prefix="/api/v1/chats")


@pytest.fixture
async def async_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    async with httpx.AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://testserver",
        headers={"Content-Type": "application/json"},
    ) as client:
        yield client


@pytest.mark.asyncio
async def test_task_hud_lifecycle_and_anti_compaction_injection(async_client: httpx.AsyncClient) -> None:
    chat_id = f"test_chat_{uuid.uuid4().hex[:8]}"

    # 1. Initially empty
    resp = await async_client.get(f"/api/v1/chats/{chat_id}/tasks")
    assert resp.status_code == 200
    data = resp.json()
    assert data["session_id"] == chat_id
    assert len(data["tasks"]) == 0
    assert data["overall_progress"] == 0
    assert data["active_task_id"] is None
    assert data["hud_injection_text"] == ""

    # 2. Add step 1
    add_req_1 = {
        "id": "step_1",
        "title": "Parse project requirements",
        "details": "Extract goals and constraints",
        "status": "in_progress",
        "progress_percent": 30,
    }
    resp1 = await async_client.post(f"/api/v1/chats/{chat_id}/tasks", json=add_req_1)
    assert resp1.status_code == 200
    t1 = resp1.json()
    assert t1["id"] == "step_1"
    assert t1["status"] == "in_progress"
    assert t1["progress_percent"] == 30

    # 3. Add step 2
    add_req_2 = {
        "id": "step_2",
        "title": "Build UI components",
        "details": "Implement React Dialog & HUD",
        "status": "pending",
        "progress_percent": 0,
    }
    resp2 = await async_client.post(f"/api/v1/chats/{chat_id}/tasks", json=add_req_2)
    assert resp2.status_code == 200

    # 4. Check aggregate status
    agg_resp = await async_client.get(f"/api/v1/chats/{chat_id}/tasks")
    assert agg_resp.status_code == 200
    agg = agg_resp.json()
    assert len(agg["tasks"]) == 2
    assert agg["active_task_id"] == "step_1"
    # Overall progress: (30 + 0) / 2 = 15%
    assert agg["overall_progress"] == 15
    assert "ANTI-COMPACTION PERSISTENT TASK HUD" in agg["hud_injection_text"]
    assert "Parse project requirements" in agg["hud_injection_text"]

    # 5. Patch step 1 to completed
    patch_req = {
        "status": "completed",
        "progress_percent": 100,
        "details": "Requirements fully parsed",
    }
    patch_resp = await async_client.patch(f"/api/v1/chats/{chat_id}/tasks/step_1", json=patch_req)
    assert patch_resp.status_code == 200
    patched = patch_resp.json()
    assert patched["status"] == "completed"
    assert patched["progress_percent"] == 100

    # 6. Verify step 2 now becomes the active task
    agg_after = (await async_client.get(f"/api/v1/chats/{chat_id}/tasks")).json()
    assert agg_after["active_task_id"] == "step_2"
    # Overall progress: (100 + 0) / 2 = 50%
    assert agg_after["overall_progress"] == 50

    # 7. Delete step 1
    del_resp = await async_client.delete(f"/api/v1/chats/{chat_id}/tasks/step_1")
    assert del_resp.status_code == 204

    # 8. Deleting again should return 404
    del_again = await async_client.delete(f"/api/v1/chats/{chat_id}/tasks/step_1")
    assert del_again.status_code == 404
