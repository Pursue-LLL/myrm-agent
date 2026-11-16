"""A goal turn the server starts for itself takes the session and carries a cancel token before its agent is built.

Checked against the real gateway, cancellation registry and goal registry; only the agent stream is a stand-in. The
chat Stop button, a pause and the emergency stop reach a turn through that session claim and that token, so a turn
without them cannot be stopped from outside. The turn also holds the session's goal provider while it runs: the agent
mounts its goal tools from it, and the goal lifecycle callbacks read it from the stream context.
"""

import asyncio
import uuid
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from myrm_agent_harness.agent.goals.protocols import GoalProvider
from myrm_agent_harness.toolkits.storage.local import LocalStorageBackend
from myrm_agent_harness.utils.runtime.cancellation import CancellationRegistry, CancelReason

from app.services.agent.gateway import AgentDrainingError, get_agent_gateway
from app.services.agent.goals import goal_controls
from app.services.agent.goals.goal_registry import GoalRegistry
from app.services.agent.goals.unattended import trigger

from .headless_turn_testkit import WAIT_SECONDS, Agent, goal_for, released, settle, start, trigger_environment


@pytest.fixture
def chat_id() -> Iterator[str]:
    chat = f"goal-turn-{uuid.uuid4().hex[:8]}"
    yield chat
    # The gateway is one per process: a failing test must not leave its session busy for the next one.
    get_agent_gateway().release_session(chat)


@pytest.fixture(autouse=True)
def storage(tmp_path: Path) -> Iterator[None]:
    """The platform storage behind the registry's provider: a throwaway directory."""
    with patch("app.platform_utils.get_storage_provider", return_value=LocalStorageBackend(str(tmp_path))):
        yield


@pytest.fixture
def background_jobs() -> Iterator[AsyncMock]:
    """The ``kill_session_jobs`` of the registry the turn asks to end a stopped turn's background jobs."""
    registry = MagicMock()
    registry.kill_session_jobs = AsyncMock(return_value=0)
    with patch("myrm_agent_harness.api.hooks.get_background_registry", return_value=registry):
        yield registry.kill_session_jobs


@pytest.fixture
def no_start_wait(monkeypatch: pytest.MonkeyPatch) -> None:
    """A start that finds its session held gives up at once instead of waiting for it."""
    monkeypatch.setattr(trigger, "_START_WAIT_SECONDS", 0.0)


@pytest.mark.asyncio
async def test_the_turn_holds_the_session_and_a_cancel_token_before_its_agent_is_built(chat_id: str) -> None:
    agent = Agent(chat_id, claims_session=False)

    with trigger_environment(agent):
        await start(chat_id)
        await asyncio.wait_for(agent.entered.wait(), timeout=WAIT_SECONDS)
        await settle()

    assert agent.session_was_active
    assert agent.turn_id is not None
    assert agent.cancel_token is not None
    assert agent.cancel_token.request_id == agent.turn_id


@pytest.mark.asyncio
async def test_the_agent_is_built_and_wired_from_the_goal_provider_the_turn_holds(chat_id: str) -> None:
    """Goal tools are mounted from the registry at build time and the goal callbacks from the stream context."""
    agent = Agent(chat_id, claims_session=False)

    with trigger_environment(agent):
        await start(chat_id)
        await asyncio.wait_for(agent.entered.wait(), timeout=WAIT_SECONDS)
        await settle()

    assert agent.registered_provider is not None
    assert agent.context_provider is agent.registered_provider
    assert GoalRegistry.get_provider(chat_id) is None


@pytest.mark.asyncio
async def test_the_provider_is_given_back_before_the_session_is(chat_id: str) -> None:
    """A message that takes the session the moment it is free must find the registry clean, not lose its provider."""
    gateway = get_agent_gateway()
    release = gateway.release_if_reserved_only
    held_when_session_freed: list[GoalProvider | None] = []

    def note_then_release(session_id: str) -> None:
        held_when_session_freed.append(GoalRegistry.get_provider(session_id))
        release(session_id)

    agent = Agent(chat_id, claims_session=False)
    with trigger_environment(agent), patch.object(gateway, "release_if_reserved_only", note_then_release):
        await start(chat_id)
        await asyncio.wait_for(agent.entered.wait(), timeout=WAIT_SECONDS)
        await settle()

    assert held_when_session_freed == [None]


@pytest.mark.asyncio
async def test_a_pause_stops_the_turn_the_server_started_through_its_cancel_token(chat_id: str) -> None:
    agent = Agent(chat_id)

    with trigger_environment(agent):
        await start(chat_id)
        await asyncio.wait_for(agent.running.wait(), timeout=WAIT_SECONDS)
        assert get_agent_gateway().get_active_message_id(chat_id) == agent.turn_id
        assert agent.cancel_token is not None
        assert not agent.cancel_token.is_cancelled

        assert goal_controls.stop_goal_turn(chat_id, goal_for(chat_id))

        assert agent.cancel_token.is_cancelled
        assert goal_controls.is_turn_stopping(chat_id)
        agent.gate.set()
        await settle()

    assert not goal_controls.is_turn_stopping(chat_id)
    assert released(chat_id, agent.turn_id)


@pytest.mark.asyncio
@pytest.mark.parametrize(("stopped", "jobs_ended"), [(True, True), (False, False)], ids=["paused", "ran_to_the_end"])
async def test_only_a_stopped_turn_ends_the_background_jobs_it_started(
    chat_id: str, background_jobs: AsyncMock, stopped: bool, jobs_ended: bool
) -> None:
    """A pause ends what the turn left running, as the chat Stop button does; a turn that finished leaves it for the goal."""
    agent = Agent(chat_id)

    with trigger_environment(agent):
        await start(chat_id)
        await asyncio.wait_for(agent.running.wait(), timeout=WAIT_SECONDS)
        if stopped:
            assert goal_controls.stop_goal_turn(chat_id, goal_for(chat_id))
        agent.gate.set()
        await settle()

    assert background_jobs.await_count == int(jobs_ended)
    if jobs_ended:
        background_jobs.assert_awaited_once_with(chat_id)
    assert released(chat_id, agent.turn_id)


@pytest.mark.asyncio
async def test_an_emergency_stop_cancels_the_turn_the_server_started(chat_id: str) -> None:
    agent = Agent(chat_id)

    with trigger_environment(agent):
        await start(chat_id)
        await asyncio.wait_for(agent.running.wait(), timeout=WAIT_SECONDS)
        assert agent.cancel_token is not None

        assert CancellationRegistry.cancel_all(CancelReason.ESTOP) >= 1

        assert agent.cancel_token.is_cancelled
        agent.gate.set()
        await settle()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("agent_kwargs", "failure_reported"),
    [
        pytest.param({}, False, id="ran_to_the_end"),
        pytest.param({"claims_session": False}, False, id="ended_without_taking_the_session"),
        pytest.param({"raises": RuntimeError("mid stream")}, True, id="failed_before_taking_the_session"),
    ],
)
async def test_the_turn_gives_back_its_session_cancel_token_and_goal_provider_however_it_ends(
    chat_id: str, agent_kwargs: dict[str, object], failure_reported: bool
) -> None:
    agent = Agent(chat_id, **agent_kwargs)  # type: ignore[arg-type]

    with trigger_environment(agent) as handler:
        await start(chat_id)
        await asyncio.wait_for(agent.entered.wait(), timeout=WAIT_SECONDS)
        agent.gate.set()
        await settle()

    assert agent.turn_id is not None
    assert agent.registered_provider is not None
    assert released(chat_id, agent.turn_id)
    assert GoalRegistry.get_provider(chat_id) is None
    assert handler.await_count == int(failure_reported)
    if failure_reported:
        handler.assert_awaited_once_with(chat_id, "g-runtime", context="runtime test")


@pytest.mark.asyncio
@pytest.mark.usefixtures("no_start_wait")
async def test_a_session_taken_by_a_message_is_left_to_it_and_nothing_is_built(chat_id: str) -> None:
    """A message that took the session first carries the goal on: the start is neither a failure nor a theft of its claim."""
    gateway = get_agent_gateway()
    gateway.reserve_session(chat_id, active_message_id="user-message")
    agent = Agent(chat_id)

    with trigger_environment(agent) as handler:
        await start(chat_id)
        await settle()

    assert agent.calls == 0
    handler.assert_not_awaited()
    assert GoalRegistry.get_provider(chat_id) is None
    assert gateway.get_active_message_id(chat_id) == "user-message"
    assert gateway.is_session_active(chat_id)


@pytest.mark.asyncio
@pytest.mark.usefixtures("no_start_wait")
async def test_a_second_start_leaves_the_first_turn_running_and_builds_nothing(chat_id: str) -> None:
    first = Agent(chat_id)
    second = Agent(chat_id)

    with trigger_environment(first) as handler:
        await start(chat_id)
        await asyncio.wait_for(first.running.wait(), timeout=WAIT_SECONDS)

        with patch("app.services.agent.streaming.ai_agent_service_stream", second):
            await start(chat_id)
            await asyncio.sleep(0.05)

        assert second.calls == 0
        assert get_agent_gateway().get_active_message_id(chat_id) == first.turn_id
        assert first.cancel_token is not None
        assert not first.cancel_token.is_cancelled
        assert first.registered_provider is not None
        assert GoalRegistry.get_provider(chat_id) is first.registered_provider
        first.gate.set()
        await settle()

    handler.assert_not_awaited()
    assert released(chat_id, first.turn_id)


@pytest.mark.asyncio
@pytest.mark.parametrize("drain_starts", ["before_the_session_is_taken", "while_the_agent_is_built"])
async def test_a_start_that_meets_a_draining_app_is_not_a_goal_failure(chat_id: str, drain_starts: str) -> None:
    gateway = get_agent_gateway()
    agent = Agent(
        chat_id, raises=AgentDrainingError("Gateway is draining") if drain_starts == "while_the_agent_is_built" else None
    )

    with (
        trigger_environment(agent) as handler,
        patch.object(gateway, "_draining", drain_starts == "before_the_session_is_taken"),
    ):
        await start(chat_id)
        await settle()

    handler.assert_not_awaited()
    assert agent.calls == int(drain_starts == "while_the_agent_is_built")
    assert released(chat_id, agent.turn_id)
    assert GoalRegistry.get_provider(chat_id) is None
