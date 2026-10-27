"""A turn the server starts by itself holds its session and a registered cancel token until it ends, however it ends.

Checked against the real gateway and cancellation registry; only the background job registry is a stand-in.
"""

import uuid
from collections.abc import Iterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from myrm_agent_harness.utils.runtime.cancellation import CancellationRegistry, CancelReason

from app.services.agent.gateway import AgentBusyError, AgentDrainingError, get_agent_gateway
from app.services.agent.turn_lease import server_turn_lease


@pytest.fixture
def chat_id() -> Iterator[str]:
    chat = f"lease-{uuid.uuid4().hex[:8]}"
    yield chat
    # The gateway is one per process: a failing test must not leave its session busy for the next one.
    get_agent_gateway().release_session(chat)


@pytest.fixture
def background_jobs() -> Iterator[AsyncMock]:
    """The ``kill_session_jobs`` of the registry the lease asks to end a stopped turn's jobs."""
    registry = MagicMock()
    registry.kill_session_jobs = AsyncMock(return_value=0)
    with patch("myrm_agent_harness.api.hooks.get_background_registry", return_value=registry):
        yield registry.kill_session_jobs


@pytest.mark.asyncio
async def test_the_turn_holds_the_session_and_a_registered_token_while_it_runs(chat_id: str) -> None:
    gateway = get_agent_gateway()

    async with server_turn_lease(chat_id, "turn-1") as token:
        assert gateway.is_session_active(chat_id)
        assert gateway.get_active_message_id(chat_id) == "turn-1"
        assert token.request_id == "turn-1"
        assert not token.is_cancelled

        # A stop finds the turn by its id, and the token the stream runs under is the one it flips.
        assert CancellationRegistry.cancel("turn-1", CancelReason.USER_CANCELLED)
        assert token.is_cancelled


@pytest.mark.asyncio
async def test_the_turn_gives_back_its_session_and_token_when_it_ends(chat_id: str) -> None:
    async with server_turn_lease(chat_id, "turn-1"):
        pass

    assert not get_agent_gateway().is_session_active(chat_id)
    assert not CancellationRegistry.cancel("turn-1", CancelReason.USER_CANCELLED)


@pytest.mark.asyncio
async def test_the_turn_gives_back_its_session_and_token_when_it_fails(chat_id: str) -> None:
    with pytest.raises(RuntimeError, match="boom"):
        async with server_turn_lease(chat_id, "turn-1"):
            raise RuntimeError("boom")

    assert not get_agent_gateway().is_session_active(chat_id)
    assert not CancellationRegistry.cancel("turn-1", CancelReason.USER_CANCELLED)


@pytest.mark.asyncio
async def test_a_busy_session_is_refused_and_its_holder_is_left_alone(chat_id: str) -> None:
    gateway = get_agent_gateway()
    gateway.reserve_session(chat_id, active_message_id="user-message")

    with pytest.raises(AgentBusyError):
        async with server_turn_lease(chat_id, "turn-1"):
            pytest.fail("the turn must not start on a session another turn holds")

    assert gateway.get_active_message_id(chat_id) == "user-message"
    assert gateway.is_session_active(chat_id)
    assert not CancellationRegistry.cancel("turn-1", CancelReason.USER_CANCELLED)


@pytest.mark.asyncio
async def test_a_draining_app_refuses_the_turn(chat_id: str) -> None:
    gateway = get_agent_gateway()

    with patch.object(gateway, "_draining", True), pytest.raises(AgentDrainingError):
        async with server_turn_lease(chat_id, "turn-1"):
            pytest.fail("the turn must not start while the application drains")

    assert not gateway.is_session_active(chat_id)


@pytest.mark.asyncio
async def test_a_session_a_message_took_after_the_stream_ended_is_not_released(chat_id: str) -> None:
    gateway = get_agent_gateway()

    async with server_turn_lease(chat_id, "turn-1"):
        # The stream ended and cleared its claim; a message took the session before the lease was given back.
        gateway.release_session(chat_id)
        gateway.reserve_session(chat_id, active_message_id="user-message")

    assert gateway.get_active_message_id(chat_id) == "user-message"
    assert gateway.is_session_active(chat_id)


@pytest.mark.asyncio
async def test_a_stopped_turn_ends_the_background_jobs_it_started(chat_id: str, background_jobs: AsyncMock) -> None:
    async with server_turn_lease(chat_id, "turn-1") as token:
        CancellationRegistry.cancel("turn-1", CancelReason.USER_CANCELLED)
        assert token.is_cancelled

    background_jobs.assert_awaited_once_with(chat_id)
    assert not get_agent_gateway().is_session_active(chat_id)


@pytest.mark.asyncio
async def test_a_turn_that_ran_to_the_end_leaves_its_background_jobs_alone(chat_id: str, background_jobs: AsyncMock) -> None:
    async with server_turn_lease(chat_id, "turn-1"):
        pass

    background_jobs.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_job_registry_failure_does_not_keep_the_session(chat_id: str, background_jobs: AsyncMock) -> None:
    background_jobs.side_effect = RuntimeError("registry unavailable")

    async with server_turn_lease(chat_id, "turn-1"):
        CancellationRegistry.cancel("turn-1", CancelReason.USER_CANCELLED)

    background_jobs.assert_awaited_once_with(chat_id)
    assert not get_agent_gateway().is_session_active(chat_id)
    assert not CancellationRegistry.cancel("turn-1", CancelReason.USER_CANCELLED)
