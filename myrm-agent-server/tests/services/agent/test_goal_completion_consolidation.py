"""Goal completion consolidation — deliverables collection on Goal COMPLETE."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.services.agent.goal_registry import ServerGoalManager


@pytest.fixture
def manager_with_session() -> ServerGoalManager:
    mock_storage = AsyncMock()
    mgr = ServerGoalManager(mock_storage, session_id="chat-1")
    mgr._storage = AsyncMock()
    return mgr


@pytest.fixture
def manager_without_session() -> ServerGoalManager:
    return ServerGoalManager(AsyncMock(), session_id=None)


class TestGoalCompletionConsolidation:
    @pytest.mark.asyncio
    async def test_consolidation_collects_deliverables(self, manager_with_session: ServerGoalManager) -> None:
        mock_deliverables = [
            {"id": "art-1", "filename": "report.docx"},
            {"id": "art-2", "filename": "data.xlsx"},
        ]
        goal = SimpleNamespace(goal_id="goal-1", metadata={}, budget=None)

        with patch(
            "app.services.agent.goal_registry._collect_session_deliverables",
            new_callable=AsyncMock,
            return_value=mock_deliverables,
        ):
            await manager_with_session._consolidate_decisions_on_completion(goal)

        assert goal.metadata["deliverables"] == mock_deliverables
        manager_with_session._storage.save_goal.assert_awaited_once_with(goal)

    @pytest.mark.asyncio
    async def test_consolidation_skips_empty_deliverables(self, manager_with_session: ServerGoalManager) -> None:
        goal = SimpleNamespace(goal_id="goal-2", metadata={})

        with patch(
            "app.services.agent.goal_registry._collect_session_deliverables",
            new_callable=AsyncMock,
            return_value=[],
        ):
            await manager_with_session._consolidate_decisions_on_completion(goal)

        assert "deliverables" not in goal.metadata

    @pytest.mark.asyncio
    async def test_consolidation_noop_without_session(self, manager_without_session: ServerGoalManager) -> None:
        goal = SimpleNamespace(goal_id="goal-3", metadata={})
        await manager_without_session._consolidate_decisions_on_completion(goal)
        assert "deliverables" not in goal.metadata

    @pytest.mark.asyncio
    async def test_consolidation_handles_error_gracefully(self, manager_with_session: ServerGoalManager) -> None:
        goal = SimpleNamespace(goal_id="goal-4", metadata={})

        with patch(
            "app.services.agent.goal_registry._collect_session_deliverables",
            new_callable=AsyncMock,
            side_effect=RuntimeError("DB connection lost"),
        ):
            await manager_with_session._consolidate_decisions_on_completion(goal)

        assert "deliverables" not in goal.metadata
