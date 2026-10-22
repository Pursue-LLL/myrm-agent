"""Unit tests for Agent Memory Asset Hub & Equipment Slots API endpoints.

[INPUT]
- fastapi.FastAPI, starlette.testclient.TestClient
- app.api.agents.memory_hub_router

[OUTPUT]
- Pytest test cases covering 4-tier asset catalog, ACL filtering, equipment slots, and ACL denial.

[POS]
tests/api/agents/test_memory_hub_api.py: Comprehensive test suite for memory asset hub endpoints.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api.agents.memory_hub_router import router as memory_hub_router


@pytest.fixture
def hub_client() -> TestClient:
    """Provide isolated TestClient fixture mounting memory_hub_router."""
    app = FastAPI()
    app.include_router(memory_hub_router, prefix="/api/v1")
    return TestClient(app)


def test_list_memory_assets_default(hub_client: TestClient) -> None:
    """Verify listing assets returns the 4-tier default cognitive assets."""
    res = hub_client.get("/api/v1/memory-hub/assets")
    assert res.status_code == 200
    assets = res.json()
    assert len(assets) >= 4

    types = {a["asset_type"] for a in assets}
    assert "chat_memory" in types
    assert "skill" in types
    assert "wiki" in types
    assert "code_graph" in types


def test_list_memory_assets_acl_filtering(hub_client: TestClient) -> None:
    """Verify private assets are shielded from unauthorized agent callers."""
    # Caller without security permission
    res_unauth = hub_client.get("/api/v1/memory-hub/assets?agent_id=unauthorized-agent")
    assert res_unauth.status_code == 200
    ids_unauth = [a["id"] for a in res_unauth.json()]
    assert "asset-chat-secret-sandbox" not in ids_unauth

    # Authorized security auditor agent
    res_auth = hub_client.get("/api/v1/memory-hub/assets?agent_id=agent-security-auditor")
    assert res_auth.status_code == 200
    ids_auth = [a["id"] for a in res_auth.json()]
    assert "asset-chat-secret-sandbox" in ids_auth


def test_create_and_get_memory_asset(hub_client: TestClient) -> None:
    """Verify creating a new cognitive Wiki asset and fetching by ID."""
    create_payload = {
        "name": "Distributed Consensus Architecture Wiki",
        "description": "Raft election algorithm and heartbeat mechanics.",
        "asset_type": "wiki",
        "acl_scope": "team",
        "content_preview": "Raft maintains log consistency across majority nodes.",
        "tags": ["raft", "consensus", "distributed"],
    }
    res = hub_client.post("/api/v1/memory-hub/assets?agent_id=agent-consensus", json=create_payload)
    assert res.status_code == 201
    created = res.json()
    assert created["name"] == create_payload["name"]
    assert created["asset_type"] == "wiki"
    assert created["acl_scope"] == "team"
    asset_id = created["id"]

    # Fetch by ID
    get_res = hub_client.get(f"/api/v1/memory-hub/assets/{asset_id}")
    assert get_res.status_code == 200
    assert get_res.json()["id"] == asset_id


def test_update_asset_acl_policy(hub_client: TestClient) -> None:
    """Verify modifying an asset's ACL scope and allowed agent list."""
    # First create a test asset
    create_res = hub_client.post(
        "/api/v1/memory-hub/assets?agent_id=owner-agent",
        json={
            "name": "Audit Logs Asset",
            "description": "Strict compliance logs",
            "asset_type": "chat_memory",
            "acl_scope": "private",
            "content_preview": "sensitive log stream",
        },
    )
    asset_id = create_res.json()["id"]

    # Update ACL to team
    update_res = hub_client.put(
        f"/api/v1/memory-hub/assets/{asset_id}/acl?agent_id=owner-agent",
        json={"acl_scope": "team", "allowed_agent_ids": []},
    )
    assert update_res.status_code == 200
    assert update_res.json()["acl_scope"] == "team"


def test_agent_equipment_slots_workflow(hub_client: TestClient) -> None:
    """Verify the 4-slot game-like loadout: get, equip matching asset, and unequip."""
    agent_id = "agent-hero-42"

    # 1. Initial equipment summary should have 4 slots and 0 equipped
    init_res = hub_client.get(f"/api/v1/agents/{agent_id}/equipment")
    assert init_res.status_code == 200
    init_data = init_res.json()
    assert init_data["agent_id"] == agent_id
    assert len(init_data["slots"]) == 4
    assert init_data["total_equipped"] == 0

    # 2. Equip Chat Memory asset into slot_chat
    equip_payload = {
        "slot_id": "slot_chat",
        "asset_id": "asset-chat-dev-prefs",
    }
    eq_res = hub_client.post(f"/api/v1/agents/{agent_id}/equipment", json=equip_payload)
    assert eq_res.status_code == 200
    eq_data = eq_res.json()
    assert eq_data["total_equipped"] == 1
    chat_slot = next(s for s in eq_data["slots"] if s["slot_id"] == "slot_chat")
    assert chat_slot["equipped_asset_id"] == "asset-chat-dev-prefs"
    assert chat_slot["equipped_asset"]["name"] == "Developer Preferences & Code Style"

    # 3. Unequip from slot_chat
    uneq_res = hub_client.delete(f"/api/v1/agents/{agent_id}/equipment/slot_chat")
    assert uneq_res.status_code == 200
    uneq_data = uneq_res.json()
    assert uneq_data["total_equipped"] == 0
    chat_slot_empty = next(s for s in uneq_data["slots"] if s["slot_id"] == "slot_chat")
    assert chat_slot_empty["equipped_asset_id"] is None


def test_equip_type_mismatch_rejected(hub_client: TestClient) -> None:
    """Verify attempting to equip skill into chat slot returns 400 Bad Request."""
    res = hub_client.post(
        "/api/v1/agents/agent-test-mismatch/equipment",
        json={"slot_id": "slot_chat", "asset_id": "asset-skill-fastapi-guru"},
    )
    assert res.status_code == 400
    assert "not allowed in slot 'slot_chat'" in res.json()["detail"]


def test_equip_private_asset_acl_denied(hub_client: TestClient) -> None:
    """Verify unauthorized agent equipping private asset returns 403 Forbidden."""
    res = hub_client.post(
        "/api/v1/agents/agent-unauthorized/equipment",
        json={"slot_id": "slot_chat", "asset_id": "asset-chat-secret-sandbox"},
    )
    assert res.status_code == 403
    assert "not authorized to equip private/restricted asset" in res.json()["detail"]
