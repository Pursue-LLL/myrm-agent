"""Integration test: kanban closure seed persists kanban_tasks_created through HTTP + DB."""

from __future__ import annotations

import asyncio
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.services.kanban import KanbanService
from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="chats")


@pytest.fixture(autouse=True)
def _reset_kanban_singleton() -> None:
    KanbanService._instance = None
    yield
    KanbanService._instance = None


@pytest.fixture(autouse=True)
def _skip_kanban_agent_validation() -> None:
    with patch.object(
        KanbanService,
        "_validate_agent_id",
        new_callable=AsyncMock,
    ):
        yield


@pytest.fixture
def client(init_test_database) -> TestClient:
    return TestClient(app)


async def _seed_visible_agent(agent_id: str, *, display_name: str) -> None:
    from app.database.models.agent import Agent
    from app.platform_utils import get_session_factory

    session_factory = get_session_factory()
    async with session_factory() as db:
        db.add(
            Agent(
                id=agent_id,
                name=display_name,
                model_selection={"model": "gpt-4o-mini"},
            ),
        )
        await db.commit()


class TestKanbanClosureSeedIntegration:
    """Verify seed endpoint writes assistant kanban_tasks_created metadata and board task."""

    def test_seed_persists_kanban_tasks_created(self, client: TestClient) -> None:
        agent_id = f"agent_{uuid.uuid4().hex[:8]}"
        asyncio.run(
            _seed_visible_agent(agent_id, display_name="Kanban Closure Seed Agent")
        )

        with patch("app.api.chats.test_fixtures.is_local_mode", return_value=True):
            seed_resp = client.post("/api/v1/chats/test/seed-kanban-closure-fixture")

        assert seed_resp.status_code == 200
        seed_body = seed_resp.json()
        chat_id = str(seed_body["chat_id"])
        board_id = str(seed_body["board_id"])
        task_id = str(seed_body["task_id"])
        task_title = str(seed_body["task_title"])
        assert chat_id.startswith("e2ekanban")

        messages_resp = client.get(f"/api/v1/chats/{chat_id}/messages")
        assert messages_resp.status_code == 200
        payload = messages_resp.json()["data"]
        messages = payload["messages"]
        assistant_messages = [item for item in messages if item["role"] == "assistant"]
        assert len(assistant_messages) == 1

        metadata = assistant_messages[0]["metadata"]
        created = metadata["kanban_tasks_created"]
        assert created == [
            {
                "task_id": task_id,
                "title": task_title,
                "board_id": board_id,
            }
        ]

        async def _assert_board_task() -> None:
            kanban = KanbanService.get_instance()
            task = await kanban.get_task(task_id)
            assert task is not None
            assert task.title == task_title
            assert task.board_id == board_id
            assert task.metadata is not None
            assert task.metadata.get("source_chat_id") == chat_id
            filtered = await kanban.list_tasks(board_id, source_chat_id=chat_id)
            assert len(filtered) == 1
            assert filtered[0].task_id == task_id

        asyncio.run(_assert_board_task())
