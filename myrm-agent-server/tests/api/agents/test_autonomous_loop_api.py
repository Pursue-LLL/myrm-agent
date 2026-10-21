"""Unit tests for Goal-Driven Autonomous Orchestration Loop API endpoints (Item 38).

[INPUT]
- app.api.agents.autonomous_loop_router.router
- app.services.agent.autonomous_loop_service.AutonomousLoopService

[OUTPUT]
- Pytest cases verifying loop initiation, step advance with watchdog gates,
  mode switching, loop completion, and session state reset.

[POS]
- myrm-agent/myrm-agent-server/tests/api/agents/test_autonomous_loop_api.py
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api.agents.autonomous_loop_router import (
    get_autonomous_loop_service,
)
from app.api.agents.autonomous_loop_router import (
    router as autonomous_loop_router,
)
from app.schemas.autonomous_loop import (
    OrchestrationModeEnum,
    StepStatusEnum,
)
from app.services.agent.autonomous_loop_service import (
    AutonomousLoopService,
)


@pytest.fixture
def loop_service() -> AutonomousLoopService:
    service = AutonomousLoopService()
    return service


@pytest.fixture
def loop_client(
    loop_service: AutonomousLoopService,
) -> Generator[TestClient, None, None]:
    app = FastAPI()
    app.include_router(autonomous_loop_router)
    app.dependency_overrides[get_autonomous_loop_service] = lambda: loop_service
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_start_and_get_autonomous_loop(loop_client: TestClient) -> None:
    chat_id = "chat_auto_01"

    # 1. Start autonomous loop
    start_resp = loop_client.post(
        f"/chats/{chat_id}/autonomous-loop/start",
        json={
            "session_id": chat_id,
            "goal_id": "goal_deep_research",
            "mode": "autonomous",
            "config": {
                "max_autonomous_steps": 5,
                "pause_on_approval": True,
                "pause_on_error": True,
            },
        },
    )
    assert start_resp.status_code == 200
    data = start_resp.json()["data"]
    assert data["session_id"] == chat_id
    assert data["goal_id"] == "goal_deep_research"
    assert data["mode"] == OrchestrationModeEnum.AUTONOMOUS.value
    assert data["is_active"] is True
    assert data["max_steps"] == 5
    assert data["current_step"] == 0

    # 2. Get state
    state_resp = loop_client.get(f"/chats/{chat_id}/autonomous-loop/state")
    assert state_resp.status_code == 200
    state_data = state_resp.json()["data"]
    assert state_data["goal_id"] == "goal_deep_research"
    assert state_data["mode"] == OrchestrationModeEnum.AUTONOMOUS.value


def test_advance_loop_step_normal(loop_client: TestClient) -> None:
    chat_id = "chat_auto_02"

    loop_client.post(
        f"/chats/{chat_id}/autonomous-loop/start",
        json={
            "session_id": chat_id,
            "goal_id": "goal_code_refactor",
            "mode": "autonomous",
            "config": {"max_autonomous_steps": 10},
        },
    )

    advance_resp = loop_client.post(
        f"/chats/{chat_id}/autonomous-loop/advance",
        json={
            "action_type": "subagent_spawn",
            "description": "Spawn backend architect agent",
            "requires_approval": False,
            "metadata": {"role": "architect"},
        },
    )
    assert advance_resp.status_code == 200
    adv_data = advance_resp.json()["data"]
    assert adv_data["current_step"] == 1
    assert adv_data["is_active"] is True
    assert len(adv_data["history"]) == 1
    assert adv_data["history"][0]["status"] == StepStatusEnum.SUCCESS.value
    assert adv_data["history"][0]["metadata"]["role"] == "architect"


def test_advance_loop_watchdog_approval_pause(loop_client: TestClient) -> None:
    chat_id = "chat_auto_03"

    loop_client.post(
        f"/chats/{chat_id}/autonomous-loop/start",
        json={
            "session_id": chat_id,
            "goal_id": "goal_prod_release",
            "mode": "autonomous",
            "config": {"max_autonomous_steps": 10, "pause_on_approval": True},
        },
    )

    # Step requires approval -> should trigger PAUSED state
    pause_resp = loop_client.post(
        f"/chats/{chat_id}/autonomous-loop/advance",
        json={
            "action_type": "git_push_main",
            "description": "Push refactored code to main branch",
            "requires_approval": True,
        },
    )
    assert pause_resp.status_code == 200
    p_data = pause_resp.json()["data"]
    assert p_data["mode"] == OrchestrationModeEnum.PAUSED.value
    assert p_data["is_active"] is False
    assert "Action requires human approval" in p_data["pause_reason"]
    assert p_data["history"][0]["status"] == StepStatusEnum.PAUSED.value


def test_mode_switch_and_completion_lifecycle(loop_client: TestClient) -> None:
    chat_id = "chat_auto_04"

    loop_client.post(
        f"/chats/{chat_id}/autonomous-loop/start",
        json={
            "session_id": chat_id,
            "goal_id": "goal_lifecycle",
            "mode": "autonomous",
        },
    )

    # Switch to SUPERVISED
    mode_resp = loop_client.post(
        f"/chats/{chat_id}/autonomous-loop/mode",
        json={"mode": "supervised", "reason": "User manual review requested"},
    )
    assert mode_resp.status_code == 200
    assert mode_resp.json()["data"]["mode"] == OrchestrationModeEnum.SUPERVISED.value
    assert mode_resp.json()["data"]["is_active"] is False

    # Complete loop
    comp_resp = loop_client.post(
        f"/chats/{chat_id}/autonomous-loop/complete",
        json={"summary": "All test suites passing with 100% coverage"},
    )
    assert comp_resp.status_code == 200
    assert comp_resp.json()["data"]["mode"] == OrchestrationModeEnum.COMPLETED.value
    assert comp_resp.json()["data"]["pause_reason"] == "All test suites passing with 100% coverage"

    # Reset
    del_resp = loop_client.delete(f"/chats/{chat_id}/autonomous-loop")
    assert del_resp.status_code == 200
    assert del_resp.json()["data"]["reset"] is True

    # 404 after reset
    get_resp = loop_client.get(f"/chats/{chat_id}/autonomous-loop/state")
    assert get_resp.status_code == 404
