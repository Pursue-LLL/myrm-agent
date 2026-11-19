"""GoalRegistry.resolve_provider: the provider the HTTP API and the IM commands read and change a session's goals through."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from myrm_agent_harness.agent.goals.types import GoalStatus
from myrm_agent_harness.toolkits.storage.local import LocalStorageBackend

from app.services.agent.goals.goal_registry import GoalRegistry


@pytest.fixture(autouse=True)
def storage(tmp_path: Path) -> Iterator[None]:
    with patch("app.platform_utils.get_storage_provider", return_value=LocalStorageBackend(str(tmp_path))):
        yield


@pytest.fixture
def chat_id(request: pytest.FixtureRequest) -> str:
    return f"resolve-provider-{request.node.name}"


def test_a_registered_provider_is_the_one_returned(chat_id: str) -> None:
    registered = GoalRegistry.register(chat_id)

    assert GoalRegistry.resolve_provider(chat_id) is registered


@pytest.mark.asyncio
async def test_a_session_between_turns_is_read_from_storage(chat_id: str) -> None:
    turn_provider = GoalRegistry.register(chat_id)
    goal = await turn_provider.create_goal(session_id=chat_id, objective="ship the weekly report")
    GoalRegistry.unregister(chat_id, turn_provider)

    stored = await GoalRegistry.resolve_provider(chat_id).get_latest_goal(chat_id)

    assert stored is not None
    assert stored.goal_id == goal.goal_id


@pytest.mark.asyncio
async def test_a_goal_completed_through_the_stand_in_collects_the_chats_deliverables(chat_id: str) -> None:
    """Approving a review between turns completes the goal through the stand-in, and the goal card lists what the chat produced."""
    turn_provider = GoalRegistry.register(chat_id)
    goal = await turn_provider.create_goal(session_id=chat_id, objective="ship the weekly report")
    GoalRegistry.unregister(chat_id, turn_provider)
    deliverables = [{"id": "a1", "filename": "report.pdf"}, {"id": "a2", "filename": "figures.png"}]

    with patch("app.services.agent.goals.goal_registry._collect_session_deliverables", AsyncMock(return_value=deliverables)):
        await GoalRegistry.resolve_provider(chat_id).update_status(goal.goal_id, GoalStatus.COMPLETE)

    stored = await GoalRegistry.resolve_provider(chat_id).get_goal(goal.goal_id)
    assert stored is not None
    assert stored.metadata["deliverables"] == deliverables


def test_the_stand_in_is_never_registered(chat_id: str) -> None:
    """A registered provider is the live handle of a running session and `GET /goals/active` lists them."""
    GoalRegistry.resolve_provider(chat_id)

    assert GoalRegistry.get_provider(chat_id) is None
    assert chat_id not in GoalRegistry.session_ids()
