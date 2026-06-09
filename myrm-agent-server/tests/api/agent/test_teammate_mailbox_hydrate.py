"""API integration tests for teammate message hydration on list_subagents."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from myrm_agent_harness.agent.coordination.mailbox import TeammateMailbox, list_teammate_history
from myrm_agent_harness.agent.sub_agents.checkpoint.saver import SubagentCheckpoint

from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="agents_api")
from app.services.chat.chat_service import ChatService


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def client() -> AsyncClient:
    transport = ASGITransport(app=app)  # type: ignore[arg-type]
    async with AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client


@pytest.fixture
def workspace(tmp_path: Path) -> str:
    return str(tmp_path)


@pytest.fixture(autouse=True)
def chat_workspace(monkeypatch: pytest.MonkeyPatch, workspace: str) -> None:
    async def ensure_default_workspace_dir(chat_id: str) -> str:
        return workspace

    monkeypatch.setattr(ChatService, "ensure_default_workspace_dir", ensure_default_workspace_dir)


def _seed_mailbox_jsonl(workspace: str, session_id: str, row: dict[str, object]) -> None:
    mailbox = TeammateMailbox(session_id, workspace)
    persist = mailbox._persist_path  # noqa: SLF001
    assert persist is not None
    persist.write_text(json.dumps(row) + "\n", encoding="utf-8")


def test_list_teammate_history_reads_jsonl(tmp_path: Path) -> None:
    session_id = "chat-hydrate-1"
    row = {
        "message_id": "m1",
        "session_id": session_id,
        "from_task_id": "worker-a",
        "to_task_id": "worker-b",
        "from_agent_type": "researcher",
        "body": "ping",
        "created_at": 100.0,
    }
    _seed_mailbox_jsonl(str(tmp_path), session_id, row)

    history = list_teammate_history(session_id, str(tmp_path), limit=10)
    assert len(history) == 1
    assert history[0]["from_task_id"] == "worker-a"


@pytest.mark.anyio
async def test_list_subagents_hydrates_teammate_messages(client: AsyncClient, workspace: str) -> None:
    chat_id = "teammate-hydrate-e2e"
    _seed_mailbox_jsonl(
        workspace,
        chat_id,
        {
            "message_id": "m-hydrate-1",
            "session_id": chat_id,
            "from_task_id": "worker-a",
            "to_task_id": "worker-b",
            "from_agent_type": "coder",
            "body": "API contract ready",
            "created_at": 200.0,
        },
    )

    checkpoint = SubagentCheckpoint(
        task_id="worker-a",
        agent_type="coder",
        session_id=chat_id,
        timestamp=1.0,
        progress=0.5,
    )
    checkpoint_b = SubagentCheckpoint(
        task_id="worker-b",
        agent_type="researcher",
        session_id=chat_id,
        timestamp=2.0,
        progress=0.3,
    )

    with patch(
        "app.api.agents.subagents.SubagentCheckpointStorage.list_checkpoints",
        new_callable=AsyncMock,
        return_value=[checkpoint, checkpoint_b],
    ):
        resp = await client.get(f"/api/v1/chats/{chat_id}/subagents")

    assert resp.status_code == 200
    data = resp.json()["data"]
    by_id = {item["task_id"]: item for item in data}
    assert "worker-a" in by_id
    assert "worker-b" in by_id
    assert by_id["worker-a"]["teammate_messages"][0]["body"] == "API contract ready"
    assert by_id["worker-b"]["teammate_messages"][0]["body"] == "API contract ready"


@pytest.mark.anyio
async def test_list_subagents_hydrate_survives_refresh(client: AsyncClient, workspace: str) -> None:
    """Simulate page refresh: two consecutive list_subagents calls return the same mailbox rows."""
    chat_id = "teammate-refresh-e2e"
    _seed_mailbox_jsonl(
        workspace,
        chat_id,
        {
            "message_id": "m-refresh-1",
            "session_id": chat_id,
            "from_task_id": "t1",
            "to_task_id": "t2",
            "from_agent_type": "planner",
            "body": "persisted after reload",
            "created_at": 300.0,
        },
    )

    ckpt = SubagentCheckpoint(
        task_id="t1",
        agent_type="planner",
        session_id=chat_id,
        timestamp=1.0,
    )

    with patch(
        "app.api.agents.subagents.SubagentCheckpointStorage.list_checkpoints",
        new_callable=AsyncMock,
        return_value=[ckpt],
    ):
        first = await client.get(f"/api/v1/chats/{chat_id}/subagents")
        second = await client.get(f"/api/v1/chats/{chat_id}/subagents")

    assert first.status_code == 200
    assert second.status_code == 200
    first_msgs = first.json()["data"][0]["teammate_messages"]
    second_msgs = second.json()["data"][0]["teammate_messages"]
    assert first_msgs == second_msgs
    assert first_msgs[0]["message_id"] == "m-refresh-1"


@pytest.mark.anyio
async def test_list_subagents_merges_active_children_and_mailbox(
    client: AsyncClient,
    workspace: str,
) -> None:
    chat_id = "teammate-active-e2e"
    _seed_mailbox_jsonl(
        workspace,
        chat_id,
        {
            "message_id": "m-active-1",
            "session_id": chat_id,
            "from_task_id": "live-a",
            "to_task_id": "live-b",
            "from_agent_type": "worker",
            "body": "live ping",
            "created_at": 400.0,
        },
    )

    mock_manager = MagicMock()
    mock_manager.list_children.return_value = [
        {"task_id": "live-a", "agent_type": "worker", "status": "running", "progress": 10},
        {"task_id": "live-b", "agent_type": "worker", "status": "running", "progress": 20},
    ]
    mock_agent = MagicMock()
    mock_agent.subagent_manager = mock_manager

    mock_info = SimpleNamespace(agent=lambda: mock_agent)

    with (
        patch("app.api.agents.subagents.get_agent_gateway") as mock_gateway,
        patch(
            "app.api.agents.subagents.SubagentCheckpointStorage.list_checkpoints",
            new_callable=AsyncMock,
            return_value=[],
        ),
    ):
        mock_gateway.return_value._session_info.get.return_value = mock_info
        resp = await client.get(f"/api/v1/chats/{chat_id}/subagents")

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data) == 2
    assert all(item.get("teammate_messages") for item in data)
