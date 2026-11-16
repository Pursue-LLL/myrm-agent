"""GoalRegistry.resolve_provider: the provider the HTTP API reads and changes a session's goals through."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from unittest.mock import patch

import pytest
from myrm_agent_harness.agent.goals.manager import GoalManager
from myrm_agent_harness.toolkits.storage.local import LocalStorageBackend

from app.services.agent.goals.goal_registry import GoalRegistry


@pytest.fixture(autouse=True)
def storage(tmp_path: Path) -> Iterator[None]:
    with patch("app.platform_utils.get_storage_provider", return_value=LocalStorageBackend(str(tmp_path))):
        yield


@pytest.fixture
def chat_id(request: pytest.FixtureRequest) -> Iterator[str]:
    session_id = f"resolve-provider-{request.node.name}"
    yield session_id
    GoalRegistry.unregister(session_id)


def test_a_registered_provider_is_the_one_returned(chat_id: str) -> None:
    registered = GoalRegistry.get_or_create_provider(chat_id)

    assert GoalRegistry.resolve_provider(chat_id) is registered


@pytest.mark.asyncio
async def test_a_session_between_turns_is_read_from_storage(chat_id: str) -> None:
    goal = await GoalRegistry.get_or_create_provider(chat_id).create_goal(session_id=chat_id, objective="ship the weekly report")
    GoalRegistry.unregister(chat_id)

    stored = await GoalRegistry.resolve_provider(chat_id).get_latest_goal(chat_id)

    assert stored is not None
    assert stored.goal_id == goal.goal_id


def test_the_stand_in_is_a_plain_manager_holding_no_running_turn_state(chat_id: str) -> None:
    assert type(GoalRegistry.resolve_provider(chat_id)) is GoalManager


def test_the_stand_in_is_never_registered(chat_id: str) -> None:
    """A registered provider is the live handle of a running session and `GET /goals/active` lists them."""
    GoalRegistry.resolve_provider(chat_id)

    assert GoalRegistry.get_provider(chat_id) is None
    assert chat_id not in GoalRegistry.session_ids()
