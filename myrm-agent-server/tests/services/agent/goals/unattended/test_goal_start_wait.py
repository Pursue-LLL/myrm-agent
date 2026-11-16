"""A goal start that finds its session still held waits, bounded, for the turn that held it.

The turn that ends a goal schedules the next start while it is still winding down, so its session is free a moment
later, not at that instant. Checked against the real gateway, goal registry and storage; only the agent stream is a
stand-in, and the polling is shortened so the tests run fast. A wait that ended on its own bound would outlast
``settle``, so the tests that expect it to end earlier fail if it does not.
"""

import asyncio
import uuid
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import patch

import pytest
from myrm_agent_harness.agent.goals.types import Goal, GoalStatus
from myrm_agent_harness.agent.security.guards.estop import EStopLevel, EStopState
from myrm_agent_harness.toolkits.storage.local import LocalStorageBackend

from app.services.agent.gateway import get_agent_gateway
from app.services.agent.goals.goal_registry import GoalRegistry
from app.services.agent.goals.unattended import trigger

from .headless_turn_testkit import WAIT_SECONDS, Agent, released, settle, start, trigger_environment

_HOLDER = "turn-winding-down"
_ESTOP = EStopState(level=EStopLevel.TOOL_FREEZE, reason="test", activated_at=0.0, activated_by="test")


@pytest.fixture
def chat_id() -> Iterator[str]:
    chat = f"goal-start-{uuid.uuid4().hex[:8]}"
    yield chat
    get_agent_gateway().release_session(chat)
    GoalRegistry.unregister(chat)


@pytest.fixture(autouse=True)
def storage(tmp_path: Path) -> Iterator[None]:
    with patch("app.platform_utils.get_storage_provider", return_value=LocalStorageBackend(str(tmp_path))):
        yield


@pytest.fixture(autouse=True)
def quick_polls(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(trigger, "_START_POLL_SECONDS", 0.02)


async def _stored_active_goal(chat: str) -> Goal:
    return await GoalRegistry.resolve_provider(chat).create_goal(chat, "Long run")


async def _meanwhile() -> None:
    """Several polls pass."""
    await asyncio.sleep(0.15)


@pytest.mark.asyncio
async def test_a_start_that_meets_a_turn_winding_down_runs_once_its_session_is_free(chat_id: str) -> None:
    gateway = get_agent_gateway()
    goal = await _stored_active_goal(chat_id)
    gateway.reserve_session(chat_id, active_message_id=_HOLDER)
    agent = Agent(chat_id, claims_session=False)

    with trigger_environment(agent) as handler:
        await start(chat_id, goal)
        await _meanwhile()
        assert agent.calls == 0

        gateway.release_session(chat_id)
        await asyncio.wait_for(agent.entered.wait(), timeout=WAIT_SECONDS)
        await settle()

    assert agent.calls == 1
    assert agent.turn_id is not None
    assert agent.turn_id != _HOLDER
    handler.assert_not_awaited()
    assert released(chat_id, agent.turn_id)
    assert GoalRegistry.get_provider(chat_id) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [GoalStatus.PAUSED, GoalStatus.COMPLETE])
async def test_a_start_gives_up_once_the_goal_has_left_active(chat_id: str, status: GoalStatus) -> None:
    gateway = get_agent_gateway()
    goal = await _stored_active_goal(chat_id)
    gateway.reserve_session(chat_id, active_message_id=_HOLDER)
    agent = Agent(chat_id)

    with trigger_environment(agent) as handler:
        await start(chat_id, goal)
        await _meanwhile()
        await GoalRegistry.resolve_provider(chat_id).update_status(goal.goal_id, status)
        await settle()

        gateway.release_session(chat_id)
        await _meanwhile()

    assert agent.calls == 0
    handler.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_start_gives_up_when_the_session_stays_held_for_the_whole_wait(
    chat_id: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    bound = 0.2
    monkeypatch.setattr(trigger, "_START_WAIT_SECONDS", bound)
    gateway = get_agent_gateway()
    goal = await _stored_active_goal(chat_id)
    gateway.reserve_session(chat_id, active_message_id="user-message")
    agent = Agent(chat_id)
    loop = asyncio.get_running_loop()

    with trigger_environment(agent) as handler:
        await start(chat_id, goal)
        began = loop.time()
        await settle()
        waited = loop.time() - began

    assert waited >= bound - 0.05
    assert agent.calls == 0
    handler.assert_not_awaited()
    assert gateway.get_active_message_id(chat_id) == "user-message"
    assert GoalRegistry.get_provider(chat_id) is None


@pytest.mark.asyncio
async def test_the_emergency_stop_ends_a_waiting_start(chat_id: str) -> None:
    gateway = get_agent_gateway()
    goal = await _stored_active_goal(chat_id)
    gateway.reserve_session(chat_id, active_message_id=_HOLDER)
    agent = Agent(chat_id)

    with trigger_environment(agent) as handler:
        await start(chat_id, goal)
        await _meanwhile()
        with patch.object(trigger, "check_estop", return_value=_ESTOP):
            await settle()

        gateway.release_session(chat_id)
        await _meanwhile()

    assert agent.calls == 0
    handler.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_draining_app_ends_a_waiting_start(chat_id: str) -> None:
    gateway = get_agent_gateway()
    goal = await _stored_active_goal(chat_id)
    gateway.reserve_session(chat_id, active_message_id=_HOLDER)
    agent = Agent(chat_id)

    with trigger_environment(agent) as handler:
        await start(chat_id, goal)
        await _meanwhile()
        with patch.object(gateway, "_draining", True):
            await settle()

        gateway.release_session(chat_id)
        await _meanwhile()

    assert agent.calls == 0
    handler.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_start_on_a_free_session_needs_neither_the_wait_nor_a_stored_goal(chat_id: str) -> None:
    """The common start: nothing holds the session, so nothing is polled and no goal is read to decide it."""
    agent = Agent(chat_id, claims_session=False)

    with trigger_environment(agent):
        await start(chat_id)
        await asyncio.wait_for(agent.entered.wait(), timeout=WAIT_SECONDS)
        await settle()

    assert agent.calls == 1
