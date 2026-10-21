"""Unit tests for A2A Trusted Peer Registry and Probe endpoints."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from myrm_agent_harness.toolkits.a2a.resolver import SSRFBlockedError
from myrm_agent_harness.toolkits.a2a.types import AgentCard

from app.database.dto import AgentCreate
from tests.support.minimal_app import build_minimal_app


@pytest.mark.asyncio
async def test_a2a_peer_crud_and_masking() -> None:
    """Test full CRUD lifecycle of A2A peer with token encryption and masking."""
    app = build_minimal_app("a2a")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Create peer
        create_payload = {
            "name": "Hermes Deep Researcher",
            "base_url": "https://hermes.example.com",
            "description": "Autonomous multi-step research agent",
            "auth_type": "bearer",
            "auth_token": "sk-secret-test-token-12345",
            "is_active": True,
        }
        res_create = await client.post("/api/v1/a2a/peers", json=create_payload)
        assert res_create.status_code == 201, res_create.text
        peer_data = res_create.json()
        peer_id = peer_data["id"]

        assert peer_data["name"] == "Hermes Deep Researcher"
        assert peer_data["base_url"] == "https://hermes.example.com"
        assert peer_data["has_token"] is True
        # Plain token must NOT leak! Masking must be present.
        assert "sk-secret-test-token-12345" not in res_create.text
        assert peer_data["masked_token"] == "sk-****2345"

        # 2. List peers
        res_list = await client.get("/api/v1/a2a/peers")
        assert res_list.status_code == 200
        peers = res_list.json()
        found = [p for p in peers if p["id"] == peer_id]
        assert len(found) == 1
        assert found[0]["name"] == "Hermes Deep Researcher"

        # 3. Get single peer
        res_get = await client.get(f"/api/v1/a2a/peers/{peer_id}")
        assert res_get.status_code == 200
        assert res_get.json()["id"] == peer_id

        # 4. Update peer
        update_payload = {
            "name": "Hermes Deep Researcher v2",
            "is_active": False,
        }
        res_update = await client.patch(f"/api/v1/a2a/peers/{peer_id}", json=update_payload)
        assert res_update.status_code == 200
        updated = res_update.json()
        assert updated["name"] == "Hermes Deep Researcher v2"
        assert updated["is_active"] is False
        assert updated["has_token"] is True

        # 5. Delete peer
        res_del = await client.delete(f"/api/v1/a2a/peers/{peer_id}")
        assert res_del.status_code == 200
        assert res_del.json()["success"] is True

        # 6. Verify 404 after deletion
        res_get_del = await client.get(f"/api/v1/a2a/peers/{peer_id}")
        assert res_get_del.status_code == 404


@pytest.mark.asyncio
async def test_a2a_peer_probe_success() -> None:
    """Test A2A probe endpoint with mocked successful AgentCard resolution."""
    mock_card = AgentCard(
        name="Remote Test Agent",
        description="A remote peer agent",
        skills=[],
    )

    app = build_minimal_app("a2a")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        with patch("myrm_agent_harness.toolkits.a2a.resolver.A2ACardResolver.resolve", new_callable=AsyncMock) as mock_resolve:
            mock_resolve.return_value = mock_card

            probe_payload = {
                "url": "https://remote.agent.org",
                "auth_token": "bearer-test-123",
            }
            res = await client.post("/api/v1/a2a/peers/probe", json=probe_payload)
            assert res.status_code == 200
            data = res.json()
            assert data["success"] is True
            assert data["status"] == "ok"
            assert data["agent_card"]["name"] == "Remote Test Agent"
            assert data["latency_ms"] >= 0


@pytest.mark.asyncio
async def test_a2a_peer_probe_ssrf_blocked() -> None:
    """Test A2A probe endpoint blocks SSRF attacks."""
    app = build_minimal_app("a2a")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        with patch("myrm_agent_harness.toolkits.a2a.resolver.A2ACardResolver.resolve", new_callable=AsyncMock) as mock_resolve:
            mock_resolve.side_effect = SSRFBlockedError("SSRF target blocked: 169.254.169.254")

            probe_payload = {
                "url": "http://169.254.169.254/latest/meta-data/",
            }
            res = await client.post("/api/v1/a2a/peers/probe", json=probe_payload)
            assert res.status_code == 200
            data = res.json()
            assert data["success"] is False
            assert data["status"] == "ssrf_blocked"
            assert "SSRF Blocked" in data["error"]


def test_agent_dto_a2a_fields() -> None:
    """Test AgentBase DTO supports a2a_enabled and a2a_trusted_peer_ids."""
    agent_in = AgentCreate(
        name="Orchestrator Agent",
        a2a_enabled=True,
        a2a_trusted_peer_ids=["peer-1", "peer-2"],
    )
    assert agent_in.a2a_enabled is True
    assert agent_in.a2a_trusted_peer_ids == ["peer-1", "peer-2"]
