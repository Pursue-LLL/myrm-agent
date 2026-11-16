"""GoalRegistry.turn_provider: the provider a turn the server starts for itself holds while it runs."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import patch

import pytest
from myrm_agent_harness.toolkits.storage.local import LocalStorageBackend

from app.services.agent.goals.goal_registry import GoalRegistry


@pytest.fixture(autouse=True)
def storage(tmp_path: Path) -> Iterator[None]:
    with patch("app.platform_utils.get_storage_provider", return_value=LocalStorageBackend(str(tmp_path))):
        yield


@pytest.fixture
def chat_id(request: pytest.FixtureRequest) -> Iterator[str]:
    session_id = f"turn-provider-{request.node.name}"
    yield session_id
    GoalRegistry.unregister(session_id)


@pytest.mark.asyncio
async def test_the_provider_is_registered_while_the_turn_runs_and_released_when_it_ends(chat_id: str) -> None:
    assert GoalRegistry.get_provider(chat_id) is None

    async with GoalRegistry.turn_provider(chat_id) as provider:
        assert GoalRegistry.get_provider(chat_id) is provider
        assert chat_id in GoalRegistry.session_ids()

    assert GoalRegistry.get_provider(chat_id) is None
    assert chat_id not in GoalRegistry.session_ids()


@pytest.mark.asyncio
async def test_the_provider_is_released_when_the_turn_raises(chat_id: str) -> None:
    with pytest.raises(RuntimeError, match="turn failed"):
        async with GoalRegistry.turn_provider(chat_id):
            raise RuntimeError("turn failed")

    assert GoalRegistry.get_provider(chat_id) is None


@pytest.mark.asyncio
async def test_the_provider_is_released_when_the_turn_is_cancelled(chat_id: str) -> None:
    entered = asyncio.Event()

    async def turn() -> None:
        async with GoalRegistry.turn_provider(chat_id):
            entered.set()
            await asyncio.Event().wait()

    task = asyncio.create_task(turn())
    await entered.wait()
    assert GoalRegistry.get_provider(chat_id) is not None

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert GoalRegistry.get_provider(chat_id) is None


@pytest.mark.asyncio
async def test_a_provider_registered_before_the_turn_is_shared_and_stays_registered(chat_id: str) -> None:
    """The IM `/goal` command registers a session's provider outside any turn; a turn on that session must not drop it."""
    registered = GoalRegistry.get_or_create_provider(chat_id)

    async with GoalRegistry.turn_provider(chat_id) as provider:
        assert provider is registered

    assert GoalRegistry.get_provider(chat_id) is registered
