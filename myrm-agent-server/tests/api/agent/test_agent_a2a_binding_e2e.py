"""Integration & unit tests for Agent A2A binding CRUD and persistence.

Verifies that `a2a_enabled` and `a2a_trusted_peer_ids` are correctly saved,
retrieved, updated, and persisted across the Agent lifecycle.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
async def async_client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


@pytest.mark.asyncio
async def test_agent_a2a_binding_crud(async_client: AsyncClient):
    """Test a2a_enabled and a2a_trusted_peer_ids full CRUD lifecycle."""
    # 1. Create agent with A2A enabled and trusted peer ids
    create_payload = {
        "name": "A2A Orchestrator Agent",
        "description": "Agent delegated to remote A2A peers",
        "a2a_enabled": True,
        "a2a_trusted_peer_ids": ["peer-1", "peer-2"],
    }
    create_resp = await async_client.post("/api/agents", json=create_payload)
    assert create_resp.status_code == 200
    created = create_resp.json()["data"]
    agent_id = created["id"]
    assert created["a2a_enabled"] is True
    assert set(created["a2a_trusted_peer_ids"]) == {"peer-1", "peer-2"}

    try:
        # 2. Get agent details and verify persistence
        get_resp = await async_client.get(f"/api/agents/{agent_id}")
        assert get_resp.status_code == 200
        detail = get_resp.json()["data"]
        assert detail["a2a_enabled"] is True
        assert set(detail["a2a_trusted_peer_ids"]) == {"peer-1", "peer-2"}

        # 3. Update agent A2A configuration
        update_payload = {
            "a2a_enabled": True,
            "a2a_trusted_peer_ids": ["peer-1", "peer-3"],
        }
        update_resp = await async_client.put(f"/api/agents/{agent_id}", json=update_payload)
        assert update_resp.status_code == 200
        updated = update_resp.json()["data"]
        assert updated["a2a_enabled"] is True
        assert set(updated["a2a_trusted_peer_ids"]) == {"peer-1", "peer-3"}

        # 4. Disable A2A
        disable_resp = await async_client.put(
            f"/api/agents/{agent_id}",
            json={"a2a_enabled": False, "a2a_trusted_peer_ids": []},
        )
        assert disable_resp.status_code == 200
        disabled = disable_resp.json()["data"]
        assert disabled["a2a_enabled"] is False
        assert disabled["a2a_trusted_peer_ids"] == []

        # 5. Verify persistence after disable
        verify_resp = await async_client.get(f"/api/agents/{agent_id}")
        assert verify_resp.status_code == 200
        assert verify_resp.json()["data"]["a2a_enabled"] is False
        assert verify_resp.json()["data"]["a2a_trusted_peer_ids"] == []

    finally:
        # Cleanup
        del_resp = await async_client.delete(f"/api/agents/{agent_id}")
        assert del_resp.status_code == 200


@pytest.mark.asyncio
async def test_agent_profile_resolver_resolves_a2a_config(async_client: AsyncClient):
    """Test that ResolvedAgentProfile correctly extracts A2A configuration."""
    from app.services.agent.profile.profile_resolver import get_agent_profile_resolver

    create_payload = {
        "name": "A2A Resolver Test Agent",
        "description": "Agent for profile resolution test",
        "a2a_enabled": True,
        "a2a_trusted_peer_ids": ["peer-alpha", "peer-beta"],
    }
    create_resp = await async_client.post("/api/agents", json=create_payload)
    assert create_resp.status_code == 200
    agent_id = create_resp.json()["data"]["id"]

    try:
        resolver = get_agent_profile_resolver()
        resolver.invalidate(agent_id)
        resolved = await resolver.resolve(agent_id)
        assert resolved is not None
        assert resolved.a2a_enabled is True
        assert set(resolved.a2a_trusted_peer_ids) == {"peer-alpha", "peer-beta"}
    finally:
        await async_client.delete(f"/api/agents/{agent_id}")


@pytest.mark.asyncio
async def test_agent_a2a_tools_mounting_and_security_gate():
    """Test that GeneralAgent mounts A2A tools and enforces peer whitelist security."""
    from datetime import datetime, timezone
    from unittest import mock
    from unittest.mock import AsyncMock, patch

    from app.ai_agents.general_agent.agent import GeneralAgent
    from app.core.types import ModelConfig
    from app.database.dto import A2APeerResponse

    now = datetime.now(timezone.utc)
    mock_peers = [
        A2APeerResponse(
            id="peer-allowed",
            name="Allowed Worker",
            base_url="https://allowed.a2a.internal",
            auth_type="bearer",
            is_active=True,
            description="Specialized in data analysis",
            created_at=now,
            updated_at=now,
        ),
        A2APeerResponse(
            id="peer-forbidden",
            name="Forbidden Worker",
            base_url="https://forbidden.a2a.internal",
            auth_type="bearer",
            is_active=True,
            description="Specialized in secret operations",
            created_at=now,
            updated_at=now,
        ),
    ]

    class FakeRegistry:
        async def list_peers(self, *, only_active: bool = False):
            return mock_peers

        async def get_peer_credentials(self, peer_id: str):
            if peer_id == "peer-allowed":
                return ("https://allowed.a2a.internal", "bearer", "secret-token-123")
            if peer_id == "peer-forbidden":
                return ("https://forbidden.a2a.internal", "bearer", "forbidden-token")
            return None

    with patch("app.services.a2a.peer_registry.get_a2a_peer_registry", return_value=FakeRegistry()):
        agent = GeneralAgent(
            model_cfg=ModelConfig(model="test/model", api_key="test-key"),
            mcp_config=None,
            a2a_enabled=True,
            a2a_trusted_peer_ids=["peer-allowed"],
        )
        tools: list[object] = []
        await agent._setup_a2a_tools(tools)
        assert len(tools) == 2
        tool_names = {getattr(t, "name", "") for t in tools}
        assert "a2a_call" in tool_names
        assert "a2a_orchestrate" in tool_names

        call_tool = next(t for t in tools if getattr(t, "name", "") == "a2a_call")

        # Calling forbidden peer must raise ValueError (Zero-trust whitelist enforcement)
        with pytest.raises(ValueError, match="not recognized or not authorized"):
            await call_tool.ainvoke({"peer": "peer-forbidden", "prompt": "test"})

        # Calling allowed peer should resolve credentials and pass to execute_a2a_call
        with patch("myrm_agent_harness.toolkits.a2a.tools.execute_a2a_call", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = {"success": True, "answer": "Done"}
            res = await call_tool.ainvoke({"peer": "Allowed Worker", "prompt": "test query"})
            assert res == {"success": True, "answer": "Done"}
            mock_call.assert_awaited_once_with(
                peer_url="https://allowed.a2a.internal",
                prompt="test query",
                bearer_token="secret-token-123",
                timeout_seconds=90.0,
                client=mock.ANY,
            )

        # Test a2a_orchestrate tool execution
        orch_tool = next(t for t in tools if getattr(t, "name", "") == "a2a_orchestrate")
        with patch("myrm_agent_harness.toolkits.a2a.tools.execute_a2a_orchestrate", new_callable=AsyncMock) as mock_orch:
            from myrm_agent_harness.toolkits.a2a.tools import FanoutMode

            mock_orch.return_value = {"success": True, "mode": "best", "total_peers": 1}
            res = await orch_tool.ainvoke(
                {
                    "peers": ["Allowed Worker"],
                    "prompt": "fanout task",
                    "mode": "best",
                }
            )
            assert res["success"] is True
            mock_orch.assert_awaited_once_with(
                peers=["https://allowed.a2a.internal"],
                prompt="fanout task",
                bearer_tokens={"https://allowed.a2a.internal": "secret-token-123"},
                mode=FanoutMode.BEST,
                timeout_seconds=90.0,
                client=mock.ANY,
            )
