"""list_subagents must include ACTIVE_SUBAGENTS rows when gateway session is gone."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="agents_api")


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def client() -> AsyncClient:
    transport = ASGITransport(app=app)  # type: ignore[arg-type]
    async with AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client


@pytest.mark.anyio
async def test_list_subagents_includes_registry_when_gateway_inactive(client: AsyncClient) -> None:
    chat_id = "registry-list-e2e"
    registry_rows = [
        {"task_id": "bg-worker", "agent_type": "bash_worker", "status": "running", "progress": 5},
    ]

    with (
        patch("app.api.agents.subagents.get_agent_gateway") as mock_gateway,
        patch(
            "app.api.agents.subagents.SubagentCheckpointStorage.list_checkpoints",
            new_callable=AsyncMock,
            return_value=[],
        ),
        patch(
            "myrm_agent_harness.agent.sub_agents.session_tree.merge_active_subagent_children",
            return_value=registry_rows,
        ) as mock_merge,
    ):
        mock_gateway.return_value._session_info.get.return_value = None
        resp = await client.get(f"/api/v1/chats/{chat_id}/subagents")

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data) == 1
    assert data[0]["task_id"] == "bg-worker"
    mock_merge.assert_called_once_with(chat_id, [])


@pytest.mark.anyio
async def test_cancel_all_subagents_uses_registry_when_gateway_inactive(client: AsyncClient) -> None:
    chat_id = "registry-cancel-all-e2e"

    with (
        patch("app.api.agents.subagents.get_agent_gateway") as mock_gateway,
        patch(
            "myrm_agent_harness.agent.sub_agents.session_tree.cancel_active_children_for_session",
            return_value=2,
        ) as mock_cancel,
    ):
        mock_gateway.return_value._session_info.get.return_value = None
        resp = await client.post(f"/api/v1/chats/{chat_id}/subagents/cancel-all")

    assert resp.status_code == 200
    assert resp.json()["data"]["cancelled"] == 2
    mock_cancel.assert_called_once_with(chat_id)


@pytest.mark.anyio
async def test_cancel_all_subagents_returns_404_when_registry_empty(client: AsyncClient) -> None:
    chat_id = "registry-cancel-all-empty"

    with (
        patch("app.api.agents.subagents.get_agent_gateway") as mock_gateway,
        patch(
            "myrm_agent_harness.agent.sub_agents.session_tree.cancel_active_children_for_session",
            return_value=0,
        ),
    ):
        mock_gateway.return_value._session_info.get.return_value = None
        resp = await client.post(f"/api/v1/chats/{chat_id}/subagents/cancel-all")

    assert resp.status_code == 404


@pytest.mark.anyio
async def test_cancel_all_subagents_chains_registry_when_gateway_active(client: AsyncClient) -> None:
    """New agent per message leaves orphan managers in ACTIVE_SUBAGENTS; cancel-all must still reach registry."""
    chat_id = "registry-cancel-all-gateway-active"

    mock_agent = MagicMock()
    mock_agent.cancel_all_children.return_value = 0

    mock_info = SimpleNamespace(agent=lambda: mock_agent)

    with (
        patch("app.api.agents.subagents.get_agent_gateway") as mock_gateway,
        patch(
            "myrm_agent_harness.agent.sub_agents.session_tree.cancel_active_children_for_session",
            return_value=2,
        ) as mock_cancel,
    ):
        mock_gateway.return_value._session_info.get.return_value = mock_info
        resp = await client.post(f"/api/v1/chats/{chat_id}/subagents/cancel-all")

    assert resp.status_code == 200
    assert resp.json()["data"]["cancelled"] == 2
    mock_agent.cancel_all_children.assert_called_once()
    mock_cancel.assert_called_once_with(chat_id)


@pytest.mark.anyio
async def test_cancel_all_subagents_sums_gateway_and_registry(client: AsyncClient) -> None:
    chat_id = "registry-cancel-all-sum"

    mock_agent = MagicMock()
    mock_agent.cancel_all_children.return_value = 1
    mock_info = SimpleNamespace(agent=lambda: mock_agent)

    with (
        patch("app.api.agents.subagents.get_agent_gateway") as mock_gateway,
        patch(
            "myrm_agent_harness.agent.sub_agents.session_tree.cancel_active_children_for_session",
            return_value=2,
        ),
    ):
        mock_gateway.return_value._session_info.get.return_value = mock_info
        resp = await client.post(f"/api/v1/chats/{chat_id}/subagents/cancel-all")

    assert resp.status_code == 200
    assert resp.json()["data"]["cancelled"] == 3


@pytest.mark.anyio
async def test_cancel_single_subagent_via_active_registry(client: AsyncClient) -> None:
    """POST /subagents/{task_id}/cancel must reach ACTIVE_SUBAGENTS manager."""
    chat_id = "single-cancel-e2e"
    task_id = "worker-1"

    mock_manager = MagicMock()
    mock_manager.cancel_child.return_value = True

    with patch("app.api.agents.subagents.ACTIVE_SUBAGENTS", {task_id: mock_manager}):
        resp = await client.post(f"/api/v1/chats/{chat_id}/subagents/{task_id}/cancel")

    assert resp.status_code == 200
    assert resp.json()["data"]["cancelled"] is True
    mock_manager.cancel_child.assert_called_once_with(task_id)


@pytest.mark.anyio
async def test_cancel_single_subagent_returns_404_when_not_active(client: AsyncClient) -> None:
    chat_id = "single-cancel-missing"
    task_id = "ghost-worker"

    with patch("app.api.agents.subagents.ACTIVE_SUBAGENTS", {}):
        resp = await client.post(f"/api/v1/chats/{chat_id}/subagents/{task_id}/cancel")

    assert resp.status_code == 404


@pytest.mark.anyio
async def test_delegation_pause_resume_routes_hit_gate_not_task_resume(client: AsyncClient) -> None:
    """delegation/resume must not match /{task_id}/resume (task_id=delegation)."""
    from myrm_agent_harness.agent.meta_tools.spawn_subagent.delegation_pause_gate import (
        resume_delegation,
    )

    chat_id = "delegation-route-integration"
    resume_delegation(chat_id)

    status = await client.get(f"/api/v1/chats/{chat_id}/subagents/delegation/status")
    assert status.status_code == 200
    assert status.json()["data"]["paused"] is False

    paused = await client.post(f"/api/v1/chats/{chat_id}/subagents/delegation/pause")
    assert paused.status_code == 200
    assert paused.json()["data"]["paused"] is True

    status = await client.get(f"/api/v1/chats/{chat_id}/subagents/delegation/status")
    assert status.json()["data"]["paused"] is True

    resumed = await client.post(f"/api/v1/chats/{chat_id}/subagents/delegation/resume")
    assert resumed.status_code == 200
    assert resumed.json()["data"]["paused"] is False

    status = await client.get(f"/api/v1/chats/{chat_id}/subagents/delegation/status")
    assert status.json()["data"]["paused"] is False
