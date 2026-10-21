"""Unit tests for Coding Agent Wave Preset Pipeline API (Item 45).

[INPUT]
- app.api.agents.coding_wave_router.router
- app.services.agent.coding_wave_service.CodingWaveService

[OUTPUT]
- Pytest test cases validating wave session creation, task status progression,
  strict stage gate enforcement (409 Conflict on incomplete tasks), and progress JSON export.

[POS]
- myrm-agent/myrm-agent-server/tests/api/agents/test_coding_wave_api.py
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api.agents.coding_wave_router import (
    get_coding_wave_service,
)
from app.api.agents.coding_wave_router import (
    router as coding_wave_router,
)
from app.services.agent.coding_wave_service import (
    CodingWaveService,
)


@pytest.fixture
def wave_service() -> CodingWaveService:
    return CodingWaveService()


@pytest.fixture
def client(wave_service: CodingWaveService) -> Generator[TestClient, None, None]:
    app = FastAPI()
    app.include_router(coding_wave_router)
    app.dependency_overrides[get_coding_wave_service] = lambda: wave_service
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_wave_session_lifecycle_api(client: TestClient) -> None:
    # 1. Initialize session
    init_resp = client.post("/chats/test_wave_chat_1/coding-wave/sessions", json={})
    assert init_resp.status_code == 200
    data = init_resp.json()["data"]
    assert data["session_id"] == "test_wave_chat_1"
    assert data["current_stage"] == "planning"
    assert data["is_completed"] is False
    assert len(data["tasks"]) == 7

    # 2. Get progress
    get_resp = client.get("/chats/test_wave_chat_1/coding-wave/progress")
    assert get_resp.status_code == 200
    assert get_resp.json()["data"]["current_stage"] == "planning"


def test_update_task_and_stage_gate_advancement_api(client: TestClient) -> None:
    client.post("/chats/test_wave_chat_2/coding-wave/sessions", json={})

    # 1. Attempt advancement while planning task is incomplete -> 409 Conflict
    bad_adv_resp = client.post("/chats/test_wave_chat_2/coding-wave/advance")
    assert bad_adv_resp.status_code == 409
    assert "Stage gate blocked" in bad_adv_resp.json()["detail"]

    # 2. Update planning task to COMPLETED
    upd_resp = client.post(
        "/chats/test_wave_chat_2/coding-wave/tasks/update",
        json={
            "task_id": "task_plan_architecture",
            "status": "completed",
            "output_summary": "Architecture blueprint approved.",
        },
    )
    assert upd_resp.status_code == 200
    assert upd_resp.json()["data"]["status"] == "completed"

    # 3. Advancement succeeds -> transitions to wave1_dev
    adv_resp = client.post("/chats/test_wave_chat_2/coding-wave/advance")
    assert adv_resp.status_code == 200
    assert adv_resp.json()["data"]["current_stage"] == "wave1_dev"


def test_export_progress_json_api(client: TestClient) -> None:
    client.post("/chats/test_wave_chat_3/coding-wave/sessions", json={})

    export_resp = client.get("/chats/test_wave_chat_3/coding-wave/export-json")
    assert export_resp.status_code == 200
    assert export_resp.headers["content-type"] == "application/json"
    data = export_resp.json()
    assert data["session_id"] == "test_wave_chat_3"
    assert data["current_stage"] == "planning"
    assert len(data["tasks"]) == 7


def test_get_default_preset_api(client: TestClient) -> None:
    resp = client.get("/agents/coding-wave/preset")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["preset_id"] == "full-stack-dev-wave"
    assert "tech-lead" in data["role_model_routing"]
    assert data["role_model_routing"]["tech-lead"] == "kimi-k3"


def test_error_handling_api(client: TestClient) -> None:
    # Query non-existent session returns 404
    missing_resp = client.get("/chats/non_existent_wave_chat/coding-wave/progress")
    assert missing_resp.status_code == 404

    # Update task with empty task_id returns 422
    bad_req = client.post(
        "/chats/test_wave_chat_err/coding-wave/tasks/update",
        json={"task_id": "", "status": "completed"},
    )
    assert bad_req.status_code == 422
