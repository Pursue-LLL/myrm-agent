"""Unit tests for Per-Project Workspace Team Blueprint Auto-Reuse API endpoints (Item 36).

[INPUT]
- app.api.agents.workspace_blueprint_router.router
- app.services.agent.workspace_blueprint_service.WorkspaceBlueprintService

[OUTPUT]
- Pytest cases verifying workspace-to-blueprint binding, auto-reuse policy resolution,
  usage recording, unbinding, and recency directory listing.

[POS]
- myrm-agent/myrm-agent-server/tests/api/agents/test_workspace_blueprint_api.py
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api.agents.workspace_blueprint_router import (
    get_workspace_blueprint_service,
)
from app.api.agents.workspace_blueprint_router import (
    router as workspace_blueprint_router,
)
from app.schemas.workspace_blueprint import (
    AutoReusePolicyEnum,
)
from app.services.agent.workspace_blueprint_service import (
    WorkspaceBlueprintService,
)


@pytest.fixture
def blueprint_service() -> WorkspaceBlueprintService:
    service = WorkspaceBlueprintService()
    service.clear()
    return service


@pytest.fixture
def blueprint_client(
    blueprint_service: WorkspaceBlueprintService,
) -> Generator[TestClient, None, None]:
    app = FastAPI()
    app.include_router(workspace_blueprint_router)
    app.dependency_overrides[get_workspace_blueprint_service] = lambda: blueprint_service
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_bind_and_resolve_workspace_blueprint(blueprint_client: TestClient) -> None:
    ws_id = "ws_project_alpha"
    bp_id = "bp_fullstack_dev"

    # 1. Bind blueprint with PROMPT_REUSE policy
    bind_resp = blueprint_client.post(
        f"/workspaces/{ws_id}/blueprints",
        json={
            "blueprint_id": bp_id,
            "team_name": "Fullstack Agile Team",
            "auto_reuse_policy": AutoReusePolicyEnum.PROMPT_REUSE.value,
            "member_count": 3,
            "total_budget_tokens": 150000,
            "project_label": "Project Alpha Microservices",
            "blueprint_snapshot": {"lead": "orchestrator", "coder": "fullstack"},
        },
    )
    assert bind_resp.status_code == 200
    bind_data = bind_resp.json()["data"]
    assert bind_data["workspace_id"] == ws_id
    assert bind_data["blueprint_id"] == bp_id
    assert bind_data["team_name"] == "Fullstack Agile Team"
    assert bind_data["auto_reuse_policy"] == AutoReusePolicyEnum.PROMPT_REUSE.value
    assert bind_data["member_count"] == 3

    # 2. Resolve active blueprint
    resolve_resp = blueprint_client.get(f"/workspaces/{ws_id}/blueprints/active")
    assert resolve_resp.status_code == 200
    res_data = resolve_resp.json()["data"]
    assert res_data["workspace_id"] == ws_id
    assert res_data["can_auto_instantiate"] is False
    assert res_data["status_label"] == "prompt_candidate"
    assert res_data["binding"] is not None
    assert res_data["binding"]["blueprint_id"] == bp_id


def test_auto_instantiate_policy_branch(blueprint_client: TestClient) -> None:
    ws_id = "ws_project_always"
    bp_id = "bp_ci_guardian"

    # Bind with ALWAYS_REUSE policy
    blueprint_client.post(
        f"/workspaces/{ws_id}/blueprints",
        json={
            "blueprint_id": bp_id,
            "team_name": "CI Guardian Team",
            "auto_reuse_policy": AutoReusePolicyEnum.ALWAYS_REUSE.value,
            "member_count": 2,
            "total_budget_tokens": 80000,
        },
    )

    resolve_resp = blueprint_client.get(f"/workspaces/{ws_id}/blueprints/active")
    assert resolve_resp.status_code == 200
    res_data = resolve_resp.json()["data"]
    assert res_data["can_auto_instantiate"] is True
    assert res_data["status_label"] == "auto_instantiable"
    assert "ALWAYS_REUSE" in res_data["resolution_rationale"]


def test_record_usage_and_recency_recommendation(blueprint_client: TestClient) -> None:
    ws1 = "ws_repo_one"
    ws2 = "ws_repo_two"

    blueprint_client.post(
        f"/workspaces/{ws1}/blueprints",
        json={
            "blueprint_id": "bp_team_1",
            "team_name": "Team One",
            "auto_reuse_policy": AutoReusePolicyEnum.PROMPT_REUSE.value,
        },
    )
    blueprint_client.post(
        f"/workspaces/{ws2}/blueprints",
        json={
            "blueprint_id": "bp_team_2",
            "team_name": "Team Two",
            "auto_reuse_policy": AutoReusePolicyEnum.PROMPT_REUSE.value,
        },
    )

    # Record usage for ws1, making it most recent
    rec_resp = blueprint_client.post(f"/workspaces/{ws1}/blueprints/record-usage")
    assert rec_resp.status_code == 200
    assert rec_resp.json()["data"]["recorded"] is True

    # Resolving an unbound workspace should recommend ws1's team
    res_unbound = blueprint_client.get("/workspaces/ws_unbound_brand_new/blueprints/active")
    assert res_unbound.status_code == 200
    unbound_data = res_unbound.json()["data"]
    assert unbound_data["status_label"] == "unbound_recommend_recent"
    assert unbound_data["binding"] is not None
    assert unbound_data["binding"]["team_name"] == "Team One"

    # List all bindings
    list_resp = blueprint_client.get("/workspaces/any/blueprints/all")
    assert list_resp.status_code == 200
    bindings = list_resp.json()["data"]["bindings"]
    assert len(bindings) == 2
    assert bindings[0]["workspace_id"] == ws1


def test_unbind_workspace_blueprint(blueprint_client: TestClient) -> None:
    ws_id = "ws_to_unbind"
    blueprint_client.post(
        f"/workspaces/{ws_id}/blueprints",
        json={
            "blueprint_id": "bp_temp",
            "team_name": "Temporary Team",
        },
    )

    # Delete binding
    del_resp = blueprint_client.delete(f"/workspaces/{ws_id}/blueprints")
    assert del_resp.status_code == 200
    assert del_resp.json()["data"]["unbound"] is True

    # After unbind, re-deleting returns False
    del_again = blueprint_client.delete(f"/workspaces/{ws_id}/blueprints")
    assert del_again.status_code == 200
    assert del_again.json()["data"]["unbound"] is False
