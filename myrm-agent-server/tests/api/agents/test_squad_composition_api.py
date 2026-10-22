"""Unit tests for Orchestrator Auto Squad Composition & Model-Deferred Wizard API endpoints.

[INPUT]
- app.api.agents.squad_composition_router.router
- app.services.agent.squad_composition_service.SquadCompositionService

[OUTPUT]
- Pytest cases verifying Phase-1 team synthesis, dynamic compute partitioning,
  Phase-2 model-deferred materialization, and session state management.

[POS]
- myrm-agent/myrm-agent-server/tests/api/agents/test_squad_composition_api.py
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api.agents.squad_composition_router import (
    get_squad_composition_service,
)
from app.api.agents.squad_composition_router import (
    router as squad_composition_router,
)
from app.services.agent.squad_composition_service import SquadCompositionService


@pytest.fixture
def squad_service() -> SquadCompositionService:
    return SquadCompositionService()


@pytest.fixture
def squad_client(
    squad_service: SquadCompositionService,
) -> Generator[TestClient, None, None]:
    app = FastAPI()
    app.include_router(squad_composition_router)
    app.dependency_overrides[get_squad_composition_service] = lambda: squad_service
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_compose_squad_blueprint_endpoint(squad_client: TestClient) -> None:
    chat_id = "chat_squad_test_01"
    goal = "Refactor multi-agent router, write unit tests, and audit security boundaries"

    resp = squad_client.post(
        f"/chats/{chat_id}/squad-composition/compose",
        json={
            "session_id": chat_id,
            "goal_description": goal,
            "total_budget_tokens": 160000,
            "total_max_cost_usd": 2.40,
            "max_descendants_per_run": 8,
        },
    )
    assert resp.status_code == 200
    data = resp.json()["data"]

    assert data["squad_id"].startswith("squad_")
    assert data["goal_description"] == goal
    assert data["total_budget_tokens"] == 160000
    assert data["total_max_cost_usd"] == 2.40
    assert len(data["members"]) >= 3

    roles = {m["role_tier"] for m in data["members"]}
    assert "orchestrator" in roles
    assert "coder" in roles
    assert "reviewer" in roles

    # Check that budget tokens add up exactly
    total_tokens = sum(m["budget_tokens"] for m in data["members"])
    assert total_tokens == 160000


def test_get_blueprint_and_list(squad_client: TestClient) -> None:
    chat_id = "chat_squad_test_02"
    compose_resp = squad_client.post(
        f"/chats/{chat_id}/squad-composition/compose",
        json={
            "session_id": chat_id,
            "goal_description": "Build high-throughput telemetry collector",
            "total_budget_tokens": 120000,
            "total_max_cost_usd": 1.50,
        },
    )
    assert compose_resp.status_code == 200
    squad_id = compose_resp.json()["data"]["squad_id"]

    # Single lookup
    get_resp = squad_client.get(f"/chats/{chat_id}/squad-composition/blueprints/{squad_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["data"]["squad_id"] == squad_id

    # List blueprints
    list_resp = squad_client.get(f"/chats/{chat_id}/squad-composition/blueprints")
    assert list_resp.status_code == 200
    all_bps = list_resp.json()["data"]
    assert len(all_bps) == 1
    assert all_bps[0]["squad_id"] == squad_id


def test_materialize_squad_phase2(squad_client: TestClient) -> None:
    chat_id = "chat_squad_test_03"
    compose_resp = squad_client.post(
        f"/chats/{chat_id}/squad-composition/compose",
        json={
            "session_id": chat_id,
            "goal_description": "Implement distributed rate limiter",
        },
    )
    squad_data = compose_resp.json()["data"]
    squad_id = squad_data["squad_id"]
    members = squad_data["members"]

    # Provide Model-Deferred choices for each role
    choices = [
        {
            "role_key": m["role_key"],
            "selected_model_id": "gpt-4o" if m["role_tier"] == "orchestrator" else "claude-3-5-sonnet",
            "custom_instructions": "Focus on zero-latency responses." if m["role_tier"] == "orchestrator" else "",
        }
        for m in members
    ]

    mat_resp = squad_client.post(
        f"/chats/{chat_id}/squad-composition/materialize",
        json={
            "session_id": chat_id,
            "squad_id": squad_id,
            "model_choices": choices,
        },
    )
    assert mat_resp.status_code == 200
    mat_data = mat_resp.json()["data"]

    assert mat_data["squad_id"] == squad_id
    assert mat_data["status"] == "active"
    assert mat_data["orchestrator_bot_id"].startswith("bot_orchestrator_")
    assert len(mat_data["members"]) == len(members)

    orch_mem = next(m for m in mat_data["members"] if m["role_tier"] == "orchestrator")
    assert orch_mem["selected_model_id"] == "gpt-4o"
    assert "Focus on zero-latency responses." in orch_mem["system_prompt"]

    # Verify query active squad
    squad_query = squad_client.get(f"/chats/{chat_id}/squad-composition/squads/{squad_id}")
    assert squad_query.status_code == 200
    assert squad_query.json()["data"]["orchestrator_bot_id"] == mat_data["orchestrator_bot_id"]


def test_error_handling_and_reset(squad_client: TestClient) -> None:
    chat_id = "chat_squad_test_04"

    # Blueprint 404
    resp404 = squad_client.get(f"/chats/{chat_id}/squad-composition/blueprints/squad_nonexistent")
    assert resp404.status_code == 404

    # Materialize non-existent squad 400
    mat_err = squad_client.post(
        f"/chats/{chat_id}/squad-composition/materialize",
        json={
            "session_id": chat_id,
            "squad_id": "squad_unknown",
            "model_choices": [{"role_key": "any", "selected_model_id": "model"}],
        },
    )
    assert mat_err.status_code == 400

    # Reset session
    del_resp = squad_client.delete(f"/chats/{chat_id}/squad-composition")
    assert del_resp.status_code == 200
    assert del_resp.json()["data"]["reset"] is True
