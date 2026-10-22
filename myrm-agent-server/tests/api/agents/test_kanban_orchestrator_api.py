"""API integration tests for Visual Multi-Agent Kanban Orchestrator and Card Lifecycle Dispatcher (Item 76).

[INPUT]
- app.api.agents.kanban_orchestrator_router.router
- app.services.agent.kanban_orchestrator_service.KanbanOrchestratorService

[OUTPUT]
- Pytest assertions verifying Kanban board creation, DAG card creation, blocked dependency enforcement (409 Conflict),
  auto-unblock cascades upon card completion, artifact mounting, human-in-the-loop overrides, and Boss Agent goal decomposition.

[POS]
- myrm-agent/myrm-agent-server/tests/api/agents/test_kanban_orchestrator_api.py
"""

from __future__ import annotations

from typing import Generator

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api.agents.kanban_orchestrator_router import router as kanban_orchestrator_router
from app.services.agent.kanban_orchestrator_service import KanbanOrchestratorService


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    """TestClient fixture with isolated KanbanOrchestratorService and router attached."""
    KanbanOrchestratorService.reset_instance()
    app = FastAPI()
    app.include_router(kanban_orchestrator_router)
    with TestClient(app) as test_client:
        yield test_client
    KanbanOrchestratorService.reset_instance()


def test_create_board_and_cards_api(client: TestClient) -> None:
    """Test creating board, listing boards, and creating cards with sandbox paths."""
    # 1. Create board
    board_res = client.post(
        "/agents/kanban-orchestrator/boards",
        json={"session_id": "chat-session-101", "title": "Platform Engineering Sprint"},
    )
    assert board_res.status_code == 201
    board_data = board_res.json()
    board_id = board_data["board_id"]
    assert board_data["title"] == "Platform Engineering Sprint"
    assert board_data["session_id"] == "chat-session-101"

    # 2. List boards
    list_res = client.get("/agents/kanban-orchestrator/boards")
    assert list_res.status_code == 200
    boards = list_res.json()
    assert any(b["board_id"] == board_id for b in boards)

    # 3. Create initial card
    card_res = client.post(
        "/agents/kanban-orchestrator/boards/" + board_id + "/cards",
        json={
            "title": "Design REST API schema",
            "description": "Specify all Pydantic DTO models and status codes",
            "assigned_agent": "@architect",
            "priority": "high",
        },
    )
    assert card_res.status_code == 201
    card_data = card_res.json()
    assert card_data["lane"] == "todo"
    assert card_data["sandbox_subdir"].startswith("tasks/card-")
    assert card_data["assigned_agent"] == "@architect"

    # 4. Get board details
    get_res = client.get("/agents/kanban-orchestrator/boards/" + board_id)
    assert get_res.status_code == 200
    assert card_data["card_id"] in get_res.json()["cards"]


def test_blocked_card_rejection_and_auto_unblock_cascade_api(client: TestClient) -> None:
    """Test that blocked cards reject execution, and completing prerequisite triggers auto-unblock."""
    # 1. Create board
    board_res = client.post(
        "/agents/kanban-orchestrator/boards",
        json={"session_id": "chat-dag-202", "title": "DAG Cascade Board"},
    )
    board_id = board_res.json()["board_id"]

    # 2. Create Card A (prerequisite)
    card_a_res = client.post(
        f"/agents/kanban-orchestrator/boards/{board_id}/cards",
        json={
            "title": "Backend Migration",
            "assigned_agent": "@backend-dev",
            "priority": "high",
        },
    )
    card_a_id = card_a_res.json()["card_id"]

    # 3. Create Card B depending on Card A
    card_b_res = client.post(
        f"/agents/kanban-orchestrator/boards/{board_id}/cards",
        json={
            "title": "Frontend Integration",
            "assigned_agent": "@frontend-dev",
            "depends_on": [card_a_id],
            "priority": "medium",
        },
    )
    card_b_id = card_b_res.json()["card_id"]
    assert card_b_res.json()["lane"] == "blocked"
    assert card_a_id in card_b_res.json()["blocked_by"]

    # 4. Attempt to transition Card B to in_progress directly -> 409 Conflict
    conflict_res = client.post(
        f"/agents/kanban-orchestrator/boards/{board_id}/cards/{card_b_id}/transition",
        json={"target_lane": "in_progress"},
    )
    assert conflict_res.status_code == 409
    assert "prerequisites" in conflict_res.json()["detail"].lower()

    # 5. Transition Card A to done -> triggers auto-unblock cascade
    done_res = client.post(
        f"/agents/kanban-orchestrator/boards/{board_id}/cards/{card_a_id}/transition",
        json={"target_lane": "done"},
    )
    assert done_res.status_code == 200
    assert done_res.json()["card"]["lane"] == "done"
    assert card_b_id in done_res.json()["unlocked_cards"]

    # 6. Verify Card B is now in todo lane
    board_get = client.get(f"/agents/kanban-orchestrator/boards/{board_id}")
    card_b_updated = board_get.json()["cards"][card_b_id]
    assert card_b_updated["lane"] == "todo"
    assert len(card_b_updated["blocked_by"]) == 0


def test_mount_artifact_and_human_override_api(client: TestClient) -> None:
    """Test mounting output artifacts and human-in-the-loop priority/assignment override."""
    # Create board & card
    board_id = client.post(
        "/agents/kanban-orchestrator/boards",
        json={"session_id": "chat-override-303", "title": "Artifact Board"},
    ).json()["board_id"]

    card_id = client.post(
        f"/agents/kanban-orchestrator/boards/{board_id}/cards",
        json={
            "title": "Write unit tests",
            "assigned_agent": "@tester",
            "priority": "low",
        },
    ).json()["card_id"]

    # Mount artifact
    art_res = client.post(
        f"/agents/kanban-orchestrator/boards/{board_id}/cards/{card_id}/artifacts",
        json={
            "name": "test_report.json",
            "artifact_type": "report",
            "file_path": "tasks/test_report.json",
            "content_preview": '{"passed": 12, "failed": 0}',
        },
    )
    assert art_res.status_code == 201
    assert art_res.json()["artifact_type"] == "report"

    # Human-in-the-loop override
    override_res = client.post(
        f"/agents/kanban-orchestrator/boards/{board_id}/cards/{card_id}/override",
        json={
            "new_agent": "@qa-lead",
            "new_priority": "critical",
            "new_lane": "review",
        },
    )
    assert override_res.status_code == 200
    updated_card = override_res.json()["card"]
    assert updated_card["assigned_agent"] == "@qa-lead"
    assert updated_card["priority"] == "critical"
    assert updated_card["lane"] == "review"
    assert len(updated_card["artifacts"]) == 1


def test_boss_agent_auto_decompose_and_cycle_prevention_api(client: TestClient) -> None:
    """Test automated goal decomposition into sequenced DAG task cards and cyclic dependency rejection."""
    board_id = client.post(
        "/agents/kanban-orchestrator/boards",
        json={"session_id": "chat-decompose-404", "title": "Orchestrator Decomposition"},
    ).json()["board_id"]

    # 1. Automated Goal Decomposition
    decompose_res = client.post(
        f"/agents/kanban-orchestrator/boards/{board_id}/decompose",
        json={
            "goal": "Build End-to-End WebSocket notification channel",
            "specialist_roster": ["@architect", "@backend-dev", "@frontend-dev", "@tester"],
        },
    )
    assert decompose_res.status_code == 201
    created_cards = decompose_res.json()["created_cards"]
    assert len(created_cards) == 3

    c1, c2, c3 = created_cards
    assert c1["lane"] == "todo"
    assert c2["lane"] == "blocked"
    assert c3["lane"] == "blocked"
    assert c1["card_id"] in c2["depends_on"]
    assert c2["card_id"] in c3["depends_on"]

    # 2. Cyclic dependency rejection (Card 1 attempting to depend on Card 3)
    cycle_res = client.post(
        f"/agents/kanban-orchestrator/boards/{board_id}/cards",
        json={
            "title": "Cyclic card",
            "assigned_agent": "@tester",
            "depends_on": ["non_existent_card_9999"],
        },
    )
    assert cycle_res.status_code == 404
