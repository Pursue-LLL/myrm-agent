"""Integration test: kanban_default_board_id propagation from request to kanban tools."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.services.agent.params.models import AgentConfigRequest, AgentRequest
from tests.api.agent.utils import get_model_selection


@pytest.fixture
def base_request() -> dict:
    return {
        "message_id": "test-msg-kanban-board",
        "chat_id": "test-chat-kanban-board",
        "query": "add a task",
        "model_selection": get_model_selection(),
    }


class TestKanbanDefaultBoardIdRequestParsing:
    def test_snake_case_parsing(self) -> None:
        cfg = AgentConfigRequest(kanban_default_board_id="board-a")
        assert cfg.kanban_default_board_id == "board-a"

    def test_camel_case_parsing(self) -> None:
        cfg = AgentConfigRequest(**{"kanbanDefaultBoardId": "board-b"})
        assert cfg.kanban_default_board_id == "board-b"


class TestKanbanDefaultBoardIdConverterIntegration:
    @pytest.mark.asyncio
    async def test_kanban_default_board_id_from_agent_config(self, base_request: dict) -> None:
        from app.services.agent.params.converter import convert_to_general_agent_params

        base_request["agent_config"] = {
            "kanbanDefaultBoardId": "board-preferred",
            "enabledBuiltinTools": ["kanban"],
        }
        request = AgentRequest(**base_request)

        params, _, _, _ = await convert_to_general_agent_params(request, [])
        assert params.kanban_default_board_id == "board-preferred"

    @pytest.mark.asyncio
    async def test_kanban_default_board_id_none_by_default(self, base_request: dict) -> None:
        from app.services.agent.params.converter import convert_to_general_agent_params

        request = AgentRequest(**base_request)

        params, _, _, _ = await convert_to_general_agent_params(request, [])
        assert params.kanban_default_board_id is None


class TestKanbanDefaultBoardIdSetupIntegration:
    @pytest.mark.asyncio
    async def test_setup_kanban_tools_uses_preferred_board_from_agent_wrapper(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from myrm_agent_harness.toolkits.kanban.stores import InMemoryKanbanStore
        from myrm_agent_harness.toolkits.kanban.types import KanbanBoard

        from app.ai_agents.general_agent.factory import _setup_kanban_tools

        store = InMemoryKanbanStore()
        await store.save_board(KanbanBoard(board_id="board-newest", name="New"))
        await store.save_board(KanbanBoard(board_id="board-preferred", name="Preferred"))

        kanban_svc = MagicMock()
        kanban_svc.store = store
        kanban_svc._dispatchers = {}

        monkeypatch.setattr(
            "app.services.kanban.service.KanbanService.get_instance",
            lambda: kanban_svc,
        )

        captured: dict[str, object] = {}

        def fake_create_kanban_tools(store_arg: object, dispatcher: object, **kwargs: object) -> list[object]:
            captured.update(kwargs)
            return []

        monkeypatch.setattr(
            "myrm_agent_harness.toolkits.kanban.create_kanban_tools",
            fake_create_kanban_tools,
        )

        agent_wrapper = SimpleNamespace(
            kanban_tool_mode="orchestrator",
            kanban_current_task_id=None,
            kanban_default_board_id="board-preferred",
            agent_id="agent-test",
        )
        tools: list[object] = []

        await _setup_kanban_tools(agent_wrapper, tools)

        assert captured.get("default_board_id") == "board-preferred"
