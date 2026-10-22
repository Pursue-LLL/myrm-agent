"""
[POS] tests/api/agents/test_split_session_goal_api.py
[INPUT] fastapi.FastAPI, starlette.testclient.TestClient, app.api.agents.split_session_goal_router, app.services.agent.goals.split_session_goal_service
[OUTPUT] test_list_split_session_templates_api, test_create_and_get_split_session_goal_api, test_advance_lifecycle_gates_and_transitions_api, test_invalid_phase_transition_guard_api

Integration test suite for Split-Session 2-Window (Window 1: Ship / Window 2: Plan) Goal templates and lifecycle transitions.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api.agents.split_session_goal_router import (
    router as split_session_goal_router,
)
from app.services.agent.goals.split_session_goal_service import (
    SplitSessionGoalService,
    get_split_session_goal_service,
)


@pytest.fixture
def split_goal_client() -> Generator[TestClient, None, None]:
    """Provide isolated TestClient fixture mounting split-session goal router."""
    service = SplitSessionGoalService()

    test_app = FastAPI()
    test_app.include_router(split_session_goal_router, prefix="/api/agents")
    test_app.dependency_overrides[get_split_session_goal_service] = lambda: service

    with TestClient(test_app) as client:
        yield client


def test_list_split_session_templates_api(split_goal_client: TestClient) -> None:
    """Verify listing declarative 2-window templates supporting English and Chinese."""
    resp = split_goal_client.get("/api/agents/goals/split-session/templates")
    assert resp.status_code == 200
    templates = resp.json()
    assert len(templates) >= 2

    tmpl_ids = [t["template_id"] for t in templates]
    assert "code_ship_architecture_plan" in tmpl_ids
    assert "feature_delivery_roadmap_plan" in tmpl_ids

    # Template structure check
    code_ship = next(t for t in templates if t["template_id"] == "code_ship_architecture_plan")
    assert "双窗口" in code_ship["name_zh"]
    assert "2-Window Split" in code_ship["name_en"]
    assert "[WINDOW 1: SHIP MODE]" in code_ship["window1_prompt_template"]
    assert "[WINDOW 2: PLAN MODE]" in code_ship["window2_prompt_template"]


def test_create_and_get_split_session_goal_api(split_goal_client: TestClient) -> None:
    """Verify instantiating a Split-Session Goal in Window 1: Ship phase."""
    create_payload = {
        "session_id": "sess-split-01",
        "template_id": "code_ship_architecture_plan",
        "title": "Migrate Payment Gateway to Stripe V2",
        "custom_window1_objective": "Ship implementation with 100% test pass rate",
    }
    resp = split_goal_client.post("/api/agents/goals/split-session", json=create_payload)
    assert resp.status_code == 201
    inst = resp.json()
    assert inst["instance_id"].startswith("split-goal-")
    assert inst["current_phase"] == "window1_shipping"
    assert inst["title"] == "Migrate Payment Gateway to Stripe V2"
    assert inst["ship_dossier"] is None
    assert inst["iteration_plan"] is None

    # Retrieve instance
    inst_id = inst["instance_id"]
    get_resp = split_goal_client.get(f"/api/agents/goals/split-session/{inst_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["instance_id"] == inst_id

    # Non-existent instance
    missing = split_goal_client.get("/api/agents/goals/split-session/non-existent-goal")
    assert missing.status_code == 404


def test_advance_lifecycle_gates_and_transitions_api(split_goal_client: TestClient) -> None:
    """Verify phase progression with acceptance gate enforcement and context handover."""
    # 1. Create Goal
    create_resp = split_goal_client.post(
        "/api/agents/goals/split-session",
        json={
            "session_id": "sess-split-lifecycle",
            "template_id": "code_ship_architecture_plan",
            "title": "Build Real-Time Device Mesh Scheduler",
        },
    )
    inst_id = create_resp.json()["instance_id"]

    # 2. Attempt Window 1 completion with failing tests: rejected by gate
    bad_advance = split_goal_client.post(
        f"/api/agents/goals/split-session/{inst_id}/advance",
        json={
            "target_phase": "window1_completed",
            "ship_dossier": {
                "deliverables": ["src/scheduler.py"],
                "test_results_summary": "1 test failed",
                "tests_passed": False,
                "modified_files": ["src/scheduler.py"],
            },
        },
    )
    assert bad_advance.status_code == 400
    assert "tests have not passed" in bad_advance.json()["detail"]

    # 3. Successful Window 1 completion with green tests
    good_ship_dossier = {
        "deliverables": ["src/scheduler.py", "tests/test_scheduler.py"],
        "test_results_summary": "5 passed in 2.1s",
        "tests_passed": True,
        "modified_files": ["src/scheduler.py", "tests/test_scheduler.py"],
        "notes": "Delivered working thread-safe scheduler",
    }
    advance_w1 = split_goal_client.post(
        f"/api/agents/goals/split-session/{inst_id}/advance",
        json={
            "target_phase": "window1_completed",
            "ship_dossier": good_ship_dossier,
        },
    )
    assert advance_w1.status_code == 200
    w1_state = advance_w1.json()
    assert w1_state["current_phase"] == "window1_completed"
    assert w1_state["ship_dossier"]["tests_passed"] is True
    assert len(w1_state["ship_dossier"]["deliverables"]) == 2

    # 4. Transition into Window 2: Planning
    advance_w2_start = split_goal_client.post(
        f"/api/agents/goals/split-session/{inst_id}/advance",
        json={"target_phase": "window2_planning"},
    )
    assert advance_w2_start.status_code == 200
    assert advance_w2_start.json()["current_phase"] == "window2_planning"

    # 5. Complete Window 2 Planning with NextIterationPlan
    plan_payload = {
        "next_objective": "Scale scheduler to handle 10,000 edge nodes with Raft consensus",
        "architecture_notes": "Refactor in-memory dictionary to distributed SQLite replication",
        "planned_task_steps": [
            "Implement Raft leader election",
            "Benchmark heartbeats under 10k QPS load",
        ],
        "estimated_tokens_savings": 45000,
    }
    finish_advance = split_goal_client.post(
        f"/api/agents/goals/split-session/{inst_id}/advance",
        json={
            "target_phase": "all_completed",
            "iteration_plan": plan_payload,
        },
    )
    assert finish_advance.status_code == 200
    final_state = finish_advance.json()
    assert final_state["current_phase"] == "all_completed"
    assert final_state["iteration_plan"]["estimated_tokens_savings"] == 45000
    assert len(final_state["iteration_plan"]["planned_task_steps"]) == 2


def test_invalid_phase_transition_guard_api(split_goal_client: TestClient) -> None:
    """Verify illegal jumps across state machine phases are rejected."""
    create_resp = split_goal_client.post(
        "/api/agents/goals/split-session",
        json={
            "session_id": "sess-split-guard",
            "template_id": "code_ship_architecture_plan",
            "title": "Guard Verification",
        },
    )
    inst_id = create_resp.json()["instance_id"]

    # Directly jumping from window1_shipping to window2_planning without completing window 1
    illegal_jump = split_goal_client.post(
        f"/api/agents/goals/split-session/{inst_id}/advance",
        json={"target_phase": "window2_planning"},
    )
    assert illegal_jump.status_code == 400
    assert "Cannot enter Window 2 planning before Window 1 is completed" in illegal_jump.json()["detail"]
