"""GoalRegistry registration: the provider a turn holds while it runs, and who may give it back."""

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
def chat_id(request: pytest.FixtureRequest) -> str:
    return f"turn-provider-{request.node.name}"


def test_a_registered_provider_is_the_running_one_of_its_session_until_it_is_given_back(chat_id: str) -> None:
    provider = GoalRegistry.register(chat_id)

    assert GoalRegistry.get_provider(chat_id) is provider
    assert chat_id in GoalRegistry.session_ids()

    GoalRegistry.unregister(chat_id, provider)

    assert GoalRegistry.get_provider(chat_id) is None
    assert chat_id not in GoalRegistry.session_ids()


def test_a_session_registered_again_has_the_new_provider_in_place_of_the_old_one(chat_id: str) -> None:
    first = GoalRegistry.register(chat_id)
    second = GoalRegistry.register(chat_id)

    assert second is not first
    assert GoalRegistry.get_provider(chat_id) is second


def test_a_provider_is_given_back_only_by_its_own_handle(chat_id: str) -> None:
    replaced = GoalRegistry.register(chat_id)
    current = GoalRegistry.register(chat_id)
    never_registered = GoalRegistry.resolve_provider("another-session")

    GoalRegistry.unregister(chat_id, replaced)
    GoalRegistry.unregister(chat_id, never_registered)

    assert GoalRegistry.get_provider(chat_id) is current


def test_giving_back_a_provider_of_a_session_without_registration_does_nothing(chat_id: str) -> None:
    GoalRegistry.unregister(chat_id, GoalRegistry.resolve_provider(chat_id))

    assert GoalRegistry.get_provider(chat_id) is None


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
async def test_a_turn_holds_a_provider_of_its_own_in_place_of_one_left_registered(chat_id: str) -> None:
    """A registration is the live handle of one turn: what an earlier turn left is replaced, not carried over."""
    left_registered = GoalRegistry.register(chat_id)

    async with GoalRegistry.turn_provider(chat_id) as provider:
        assert provider is not left_registered
        assert GoalRegistry.get_provider(chat_id) is provider

    assert GoalRegistry.get_provider(chat_id) is None


@pytest.mark.asyncio
async def test_the_late_release_of_an_earlier_turn_leaves_the_running_turn_registered(chat_id: str) -> None:
    """The gateway gives a chat turn's session back before the turn's teardown ends, so the server can start the next
    turn of the session while the earlier one is still winding down: its release must not drop the running turn."""
    earlier = GoalRegistry.register(chat_id)

    async with GoalRegistry.turn_provider(chat_id) as provider:
        GoalRegistry.unregister(chat_id, earlier)

        assert GoalRegistry.get_provider(chat_id) is provider
        assert chat_id in GoalRegistry.session_ids()

    assert GoalRegistry.get_provider(chat_id) is None
