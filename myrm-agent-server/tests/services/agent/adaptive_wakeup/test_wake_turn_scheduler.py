"""A settled background task wakes the agent once, when the chat is free, under a lease the Stop button can reach.

Checked against the real gateway, cancellation registry and wake budget; only the part that needs a model (building
the agent and streaming its turn), the emergency stop file and the daily budget are stand-ins.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from myrm_agent_harness.utils.runtime.cancellation import CancellationRegistry, CancellationToken, CancelReason

from app.services.agent.adaptive_wakeup import get_adaptive_wakeup_service, wake_turn_scheduler
from app.services.agent.adaptive_wakeup.wake_turn_scheduler import schedule_wake_turn
from app.services.agent.gateway import get_agent_gateway
from app.services.agent.wakeup_handler import ServerWakeupHandler


@dataclass
class StreamCall:
    session_id: str
    agent_id: str
    turn_id: str
    cancel_token: CancellationToken
    holds_chat: bool


@pytest.fixture
def chat_id() -> Iterator[str]:
    chat = f"wake-{uuid.uuid4().hex[:8]}"
    yield chat
    # Gateway and wake budget are one per process: a failing test must not leave its chat busy or stopped for the next.
    get_agent_gateway().release_session(chat)
    wake_turn_scheduler._waiting.pop(chat, None)
    get_adaptive_wakeup_service().reset_session(chat)


@pytest.fixture(autouse=True)
def quiet_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(wake_turn_scheduler, "_POLL_INTERVAL_SECONDS", 0.01)
    monkeypatch.setattr(wake_turn_scheduler, "check_estop", lambda: None)
    monkeypatch.setattr("app.services.budget.enforcer.should_block_execution", AsyncMock(return_value=False))
    registry = MagicMock()
    registry.kill_session_jobs = AsyncMock(return_value=0)
    monkeypatch.setattr("myrm_agent_harness.api.hooks.get_background_registry", lambda: registry)


@pytest.fixture
def background_jobs() -> AsyncMock:
    from myrm_agent_harness.api.hooks import get_background_registry

    return cast("AsyncMock", get_background_registry().kill_session_jobs)


@pytest.fixture
def streamed(monkeypatch: pytest.MonkeyPatch) -> list[StreamCall]:
    """What the wake turn asked the handler to stream; the handler itself needs a model."""
    calls: list[StreamCall] = []

    async def fake_stream(
        _self: ServerWakeupHandler, session_id: str, agent_id: str, turn_id: str, cancel_token: CancellationToken
    ) -> None:
        calls.append(
            StreamCall(session_id, agent_id, turn_id, cancel_token, holds_chat=get_agent_gateway().is_session_active(session_id))
        )

    monkeypatch.setattr(ServerWakeupHandler, "stream_wake_turn", fake_stream)
    return calls


async def settle() -> None:
    """Let every queued wake turn finish, including ones a running turn queued."""
    async with asyncio.timeout(5):
        while wake_turn_scheduler._tasks:
            await asyncio.gather(*list(wake_turn_scheduler._tasks))


@pytest.mark.asyncio
async def test_a_free_chat_is_woken_under_the_turn_lease(chat_id: str, streamed: list[StreamCall]) -> None:
    assert schedule_wake_turn(chat_id, "agent-1") is True
    await settle()

    assert len(streamed) == 1
    call = streamed[0]
    assert (call.session_id, call.agent_id) == (chat_id, "agent-1")
    # The chat Stop button finds the turn by chat id, and the token the stream runs under is the one it flips.
    assert call.holds_chat
    assert call.cancel_token.request_id == call.turn_id
    assert not get_agent_gateway().is_session_active(chat_id)
    assert not CancellationRegistry.cancel(call.turn_id, CancelReason.USER_CANCELLED)


@pytest.mark.asyncio
async def test_a_busy_chat_is_woken_only_after_its_turn_ends(chat_id: str, streamed: list[StreamCall]) -> None:
    gateway = get_agent_gateway()
    gateway.reserve_session(chat_id, active_message_id="user-turn")

    schedule_wake_turn(chat_id, "agent-1")
    await asyncio.sleep(0.1)
    assert streamed == []
    assert gateway.get_active_message_id(chat_id) == "user-turn"

    gateway.release_session(chat_id)
    await settle()

    assert len(streamed) == 1


@pytest.mark.asyncio
async def test_settlements_that_land_while_a_wake_is_queued_share_it(chat_id: str, streamed: list[StreamCall]) -> None:
    get_agent_gateway().reserve_session(chat_id, active_message_id="user-turn")

    assert schedule_wake_turn(chat_id, "agent-1") is True
    assert schedule_wake_turn(chat_id, "agent-1") is False
    assert schedule_wake_turn(chat_id, "agent-1") is False
    get_agent_gateway().release_session(chat_id)
    await settle()

    assert len(streamed) == 1


@pytest.mark.asyncio
async def test_a_settlement_during_a_wake_turn_queues_the_next_one_behind_it(
    chat_id: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    gateway = get_agent_gateway()
    running = 0
    overlapped = False
    runs = 0

    async def fake_stream(_self: ServerWakeupHandler, session_id: str, agent_id: str, *_rest: object) -> None:
        nonlocal running, overlapped, runs
        running += 1
        overlapped = overlapped or running > 1
        runs += 1
        if runs == 1:
            assert schedule_wake_turn(session_id, agent_id) is True
            await asyncio.sleep(0.05)
            assert gateway.is_session_active(session_id)
        running -= 1

    monkeypatch.setattr(ServerWakeupHandler, "stream_wake_turn", fake_stream)

    schedule_wake_turn(chat_id, "agent-1")
    await settle()

    assert runs == 2
    assert not overlapped


@pytest.mark.asyncio
async def test_a_wake_queued_behind_a_running_one_still_answers_only_what_the_user_has_not_read(
    chat_id: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    runs = 0

    async def fake_stream(_self: ServerWakeupHandler, session_id: str, agent_id: str, *_rest: object) -> None:
        nonlocal runs
        runs += 1
        if runs == 1:
            assert schedule_wake_turn(session_id, agent_id) is True
            await asyncio.sleep(0.01)
            # The user's turn read that notice before the queued wake got the chat.
            get_adaptive_wakeup_service().record_human_turn(session_id)
            await asyncio.sleep(0.01)

    monkeypatch.setattr(ServerWakeupHandler, "stream_wake_turn", fake_stream)

    schedule_wake_turn(chat_id, "agent-1")
    await settle()

    assert runs == 1


@pytest.mark.asyncio
async def test_a_settlement_after_a_wake_turn_ended_joins_the_wake_queued_behind_it(
    chat_id: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The queued wake only looks again every 0.2s, so it is still waiting when the first one has ended.
    monkeypatch.setattr(wake_turn_scheduler, "_POLL_INTERVAL_SECONDS", 0.2)
    runs = 0

    async def fake_stream(_self: ServerWakeupHandler, session_id: str, agent_id: str, *_rest: object) -> None:
        nonlocal runs
        runs += 1
        if runs == 1:
            assert schedule_wake_turn(session_id, agent_id) is True
            await asyncio.sleep(0.02)

    monkeypatch.setattr(ServerWakeupHandler, "stream_wake_turn", fake_stream)

    schedule_wake_turn(chat_id, "agent-1")
    await asyncio.sleep(0.1)
    assert not get_agent_gateway().is_session_active(chat_id)

    assert schedule_wake_turn(chat_id, "agent-1") is False
    await settle()

    assert runs == 2


@pytest.mark.asyncio
async def test_a_stop_during_the_wake_turn_reaches_it_and_ends_its_background_jobs(
    chat_id: str, monkeypatch: pytest.MonkeyPatch, background_jobs: AsyncMock
) -> None:
    started = asyncio.Event()
    outcome: list[bool] = []

    async def fake_stream(
        _self: ServerWakeupHandler, _session: str, _agent: str, _turn: str, cancel_token: CancellationToken
    ) -> None:
        started.set()
        async with asyncio.timeout(5):
            while not cancel_token.is_cancelled:
                await asyncio.sleep(0.01)
        outcome.append(cancel_token.cancel_reason == CancelReason.USER_CANCELLED)

    monkeypatch.setattr(ServerWakeupHandler, "stream_wake_turn", fake_stream)

    schedule_wake_turn(chat_id, "agent-1")
    await started.wait()
    turn_id = get_agent_gateway().get_active_message_id(chat_id)
    assert turn_id is not None
    assert CancellationRegistry.cancel(turn_id, CancelReason.USER_CANCELLED)
    await settle()

    assert outcome == [True]
    background_jobs.assert_awaited_once_with(chat_id)
    assert not get_agent_gateway().is_session_active(chat_id)


@pytest.mark.asyncio
async def test_a_stop_while_the_wake_waits_keeps_it_from_running(chat_id: str, streamed: list[StreamCall]) -> None:
    gateway = get_agent_gateway()
    gateway.reserve_session(chat_id, active_message_id="user-turn")
    schedule_wake_turn(chat_id, "agent-1")

    get_adaptive_wakeup_service().record_user_stop(chat_id)
    gateway.release_session(chat_id)
    await settle()

    assert streamed == []
    assert not gateway.is_session_active(chat_id)


@pytest.mark.asyncio
async def test_a_message_the_user_wrote_after_the_notice_keeps_the_wake_from_running(
    chat_id: str, streamed: list[StreamCall]
) -> None:
    gateway = get_agent_gateway()
    gateway.reserve_session(chat_id, active_message_id="user-turn")
    schedule_wake_turn(chat_id, "agent-1")

    # The user's own turn read the notice already; waking again would answer it twice.
    get_adaptive_wakeup_service().record_human_turn(chat_id)
    gateway.release_session(chat_id)
    await settle()

    assert streamed == []


@pytest.mark.asyncio
async def test_a_message_the_user_wrote_before_the_notice_does_not_keep_the_wake_from_running(
    chat_id: str, streamed: list[StreamCall]
) -> None:
    get_adaptive_wakeup_service().record_human_turn(chat_id)
    await asyncio.sleep(0.01)

    schedule_wake_turn(chat_id, "agent-1")
    await settle()

    assert len(streamed) == 1


@pytest.mark.parametrize(
    ("arm", "reason"),
    [
        pytest.param(
            lambda monkeypatch: monkeypatch.setattr(wake_turn_scheduler, "check_estop", lambda: object()),
            "emergency stop",
            id="emergency-stop",
        ),
        pytest.param(
            lambda monkeypatch: monkeypatch.setattr(
                "app.services.budget.enforcer.should_block_execution", AsyncMock(return_value=True)
            ),
            "daily budget",
            id="daily-budget",
        ),
    ],
)
@pytest.mark.asyncio
async def test_the_wake_does_not_run_while_it_is_forbidden(
    chat_id: str,
    streamed: list[StreamCall],
    monkeypatch: pytest.MonkeyPatch,
    arm: Callable[[pytest.MonkeyPatch], None],
    reason: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    arm(monkeypatch)

    with caplog.at_level("INFO", logger=wake_turn_scheduler.logger.name):
        schedule_wake_turn(chat_id, "agent-1")
        await settle()

    assert streamed == []
    assert reason in caplog.text
    assert not get_agent_gateway().is_session_active(chat_id)


@pytest.mark.asyncio
async def test_a_wake_that_waited_too_long_is_dropped_and_leaves_the_chat_alone(
    chat_id: str, streamed: list[StreamCall], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(wake_turn_scheduler, "_MAX_WAIT_SECONDS", 0.05)
    gateway = get_agent_gateway()
    gateway.reserve_session(chat_id, active_message_id="user-turn")

    schedule_wake_turn(chat_id, "agent-1")
    await settle()

    assert streamed == []
    assert gateway.get_active_message_id(chat_id) == "user-turn"
    assert chat_id not in wake_turn_scheduler._waiting
    # The next settlement may queue again.
    assert schedule_wake_turn(chat_id, "agent-1") is True
    gateway.release_session(chat_id)
    await settle()
    assert len(streamed) == 1


@pytest.mark.asyncio
async def test_a_draining_application_starts_no_wake(chat_id: str, streamed: list[StreamCall]) -> None:
    gateway = get_agent_gateway()
    gateway._draining = True
    try:
        schedule_wake_turn(chat_id, "agent-1")
        await settle()
    finally:
        gateway._draining = False

    assert streamed == []
    assert chat_id not in wake_turn_scheduler._waiting


@pytest.mark.asyncio
async def test_a_failing_wake_turn_gives_the_chat_back(chat_id: str, monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_stream(*_args: object) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(ServerWakeupHandler, "stream_wake_turn", fake_stream)

    schedule_wake_turn(chat_id, "agent-1")
    await settle()

    assert not get_agent_gateway().is_session_active(chat_id)
    assert chat_id not in wake_turn_scheduler._waiting
    assert schedule_wake_turn(chat_id, "agent-1") is True
    await settle()
