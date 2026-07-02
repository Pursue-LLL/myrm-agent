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
