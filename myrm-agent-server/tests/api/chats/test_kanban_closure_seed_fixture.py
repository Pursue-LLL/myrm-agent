from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="chats")


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


class TestChatsKanbanClosureSeedFixture:
    """HTTP tests for local-only Kanban Chat↔Board closure Chrome E2E seed (no LLM)."""

    def test_seed_kanban_closure_fixture_http_endpoint(self, client: TestClient) -> None:
        fake_agent = MagicMock()
        fake_agent.id = "agent-e2e-kanban"
        fake_board = MagicMock()
        fake_board.board_id = "board-e2e-1"
        fake_task = MagicMock()
        fake_task.task_id = "task-e2e-1"

        with (
            patch("app.api.chats.test_fixtures.is_local_mode", return_value=True),
            patch(
                "app.api.chats.test_fixtures.AgentService.get_agent_list",
                new_callable=AsyncMock,
                return_value=([fake_agent], 1),
            ),
            patch(
                "app.api.chats.test_fixtures.ChatService.create_or_update_chat",
                new_callable=AsyncMock,
            ),
            patch(
                "app.api.chats.test_fixtures.ChatService.append_message",
                new_callable=AsyncMock,
            ) as append_message,
            patch("app.api.chats.test_fixtures.KanbanService.get_instance") as get_kanban,
        ):
            kanban = MagicMock()
            kanban.create_board = AsyncMock(return_value=fake_board)
            kanban.add_task = AsyncMock(return_value=fake_task)
            get_kanban.return_value = kanban

            resp = client.post("/api/v1/chats/test/seed-kanban-closure-fixture")

        assert resp.status_code == 200
        body = resp.json()
        chat_id = body["chat_id"]
        assert chat_id.startswith("e2ekanban")
        assert body["board_id"] == "board-e2e-1"
        assert body["task_id"] == "task-e2e-1"
        assert body["task_title"].startswith("Closure task ")
        assert body["ui_path"] == f"/{chat_id}"
        assert body["board_deep_link_path"] == (
            f"/settings/kanban?source_chat={chat_id}&board_id=board-e2e-1"
        )
        assert append_message.await_count == 2
        assistant_call = append_message.await_args_list[1]
        extra_data = assistant_call.kwargs["extra_data"]
        assert extra_data["kanban_tasks_created"] == [
            {
                "task_id": "task-e2e-1",
                "title": body["task_title"],
                "board_id": "board-e2e-1",
            }
        ]

    def test_seed_kanban_closure_fixture_hidden_outside_local_mode(self, client: TestClient) -> None:
        with patch("app.api.chats.test_fixtures.is_local_mode", return_value=False):
            resp = client.post("/api/v1/chats/test/seed-kanban-closure-fixture")
        assert resp.status_code == 404
