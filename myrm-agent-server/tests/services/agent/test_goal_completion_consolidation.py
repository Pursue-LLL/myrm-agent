"""Goal completion consolidation — planner removed, no-op path."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.agent.goal_registry import ServerGoalManager


@pytest.fixture
def manager() -> ServerGoalManager:
    return ServerGoalManager(AsyncMock())


class TestGoalCompletionConsolidation:
    @pytest.mark.asyncio
    async def test_consolidation_is_noop_after_planner_removal(self, manager: ServerGoalManager) -> None:
        goal = SimpleNamespace(session_id="chat-1", goal_id="goal-1")
        await manager._consolidate_decisions_on_completion(goal)
