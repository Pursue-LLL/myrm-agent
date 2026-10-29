"""A settled background task wakes the agent once, when the chat is free, under a lease the Stop button can reach.

Checked against the real gateway and cancellation registry; the only stand-in is the runner, which is what decides
whether and how the turn runs.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from myrm_agent_harness.utils.runtime.cancellation import CancellationRegistry, CancellationToken, CancelReason

from app.services.agent.adaptive_wakeup import wake_turn_scheduler
from app.services.agent.adaptive_wakeup.chat_busy import set_chat_busy_probe
from app.services.agent.adaptive_wakeup.wake_turn_scheduler import schedule_wake_turn
from app.services.agent.gateway import get_agent_gateway


@dataclass
class RunCall:
    chat_id: str
    turn_id: str
    cancel_token: CancellationToken
    settled_at: datetime
    holds_chat: bool


@pytest.fixture
def chat_id() -> Iterator[str]:
    chat = f"wake-{uuid.uuid4().hex[:8]}"
    yield chat
    # The gateway is one per process: a failing test must not leave its chat busy for the next.
    get_agent_gateway().release_session(chat)
    wake_turn_scheduler._waiting.pop(chat, None)


@pytest.fixture(autouse=True)
def quiet_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(wake_turn_scheduler, "_POLL_INTERVAL_SECONDS", 0.01)
    registry = MagicMock()
    registry.kill_session_jobs = AsyncMock(return_value=0)
    monkeypatch.setattr("myrm_agent_harness.api.hooks.get_background_registry", lambda: registry)


@pytest.fixture
def background_jobs() -> AsyncMock:
    from myrm_agent_harness.api.hooks import get_background_registry

    return cast("AsyncMock", get_background_registry().kill_session_jobs)


@pytest.fixture
def ran() -> list[RunCall]:
    return []


@pytest.fixture
def run(ran: list[RunCall]) -> wake_turn_scheduler.WakeTurnRunner:
    """A runner that records what it was started with."""

    async def record(chat_id: str, turn_id: str, cancel_token: CancellationToken, settled_at: datetime) -> None:
        ran.append(RunCall(chat_id, turn_id, cancel_token, settled_at, holds_chat=get_agent_gateway().is_session_active(chat_id)))

    return record


async def settle() -> None:
    """Let every queued wake turn finish, including ones a running turn queued."""
    async with asyncio.timeout(5):
        while wake_turn_scheduler._tasks:
            await asyncio.gather(*list(wake_turn_scheduler._tasks))


@pytest.mark.asyncio
async def test_a_free_chat_is_woken_under_the_turn_lease(
    chat_id: str, ran: list[RunCall], run: wake_turn_scheduler.WakeTurnRunner
) -> None:
    schedule_wake_turn(chat_id, run)
    await settle()

    assert len(ran) == 1
    call = ran[0]
    assert call.chat_id == chat_id
    # The chat Stop button finds the turn by chat id, and the token the runner works under is the one it flips.
    assert call.holds_chat
    assert call.cancel_token.request_id == call.turn_id
    assert not get_agent_gateway().is_session_active(chat_id)
    assert not CancellationRegistry.cancel(call.turn_id, CancelReason.USER_CANCELLED)


@pytest.mark.asyncio
async def test_a_busy_chat_is_woken_only_after_its_turn_ends(
    chat_id: str, ran: list[RunCall], run: wake_turn_scheduler.WakeTurnRunner
) -> None:
    gateway = get_agent_gateway()
    gateway.reserve_session(chat_id, active_message_id="user-turn")

    schedule_wake_turn(chat_id, run)
    await asyncio.sleep(0.1)
    assert ran == []
    assert gateway.get_active_message_id(chat_id) == "user-turn"

    gateway.release_session(chat_id)
    await settle()

    assert len(ran) == 1


@pytest.mark.asyncio
async def test_settlements_that_land_while_a_wake_is_queued_share_it_and_the_turn_answers_the_latest(
    chat_id: str, ran: list[RunCall], run: wake_turn_scheduler.WakeTurnRunner
) -> None:
    get_agent_gateway().reserve_session(chat_id, active_message_id="user-turn")

    schedule_wake_turn(chat_id, run)
    schedule_wake_turn(chat_id, run)
    last_settlement = datetime.now(tz=UTC)
    schedule_wake_turn(chat_id, run)
    get_agent_gateway().release_session(chat_id)
    await settle()

    assert len(ran) == 1
    assert ran[0].settled_at >= last_settlement


@pytest.mark.asyncio
async def test_a_settlement_during_a_wake_turn_queues_the_next_one_behind_it(chat_id: str) -> None:
    gateway = get_agent_gateway()
    running = 0
    overlapped = False
    runs = 0

    async def fake_run(session: str, _turn: str, _token: CancellationToken, _settled_at: datetime) -> None:
        nonlocal running, overlapped, runs
        running += 1
        overlapped = overlapped or running > 1
        runs += 1
        if runs == 1:
            schedule_wake_turn(session, fake_run)
            await asyncio.sleep(0.05)
            assert gateway.is_session_active(session)
        running -= 1

    schedule_wake_turn(chat_id, fake_run)
    await settle()

    assert runs == 2
    assert not overlapped


@pytest.mark.asyncio
async def test_a_settlement_after_a_wake_turn_ended_joins_the_wake_queued_behind_it(
    chat_id: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The queued wake only looks again every 0.2s, so it is still waiting when the first one has ended.
    monkeypatch.setattr(wake_turn_scheduler, "_POLL_INTERVAL_SECONDS", 0.2)
    runs = 0

    async def fake_run(session: str, _turn: str, _token: CancellationToken, _settled_at: datetime) -> None:
        nonlocal runs
        runs += 1
        if runs == 1:
            schedule_wake_turn(session, fake_run)
            await asyncio.sleep(0.02)

    schedule_wake_turn(chat_id, fake_run)
    await asyncio.sleep(0.1)
    assert not get_agent_gateway().is_session_active(chat_id)

    schedule_wake_turn(chat_id, fake_run)
    await settle()

    assert runs == 2


@pytest.mark.asyncio
async def test_a_stop_during_the_wake_turn_reaches_it_and_ends_its_background_jobs(
    chat_id: str, background_jobs: AsyncMock
) -> None:
    started = asyncio.Event()
    outcome: list[bool] = []

    async def fake_run(_session: str, _turn: str, cancel_token: CancellationToken, _settled_at: datetime) -> None:
        started.set()
        async with asyncio.timeout(5):
            while not cancel_token.is_cancelled:
                await asyncio.sleep(0.01)
        outcome.append(cancel_token.cancel_reason == CancelReason.USER_CANCELLED)

    schedule_wake_turn(chat_id, fake_run)
    await started.wait()
    turn_id = get_agent_gateway().get_active_message_id(chat_id)
    assert turn_id is not None
    assert CancellationRegistry.cancel(turn_id, CancelReason.USER_CANCELLED)
    await settle()

    assert outcome == [True]
    background_jobs.assert_awaited_once_with(chat_id)
    assert not get_agent_gateway().is_session_active(chat_id)


@pytest.mark.asyncio
async def test_a_wake_that_waited_too_long_is_dropped_and_leaves_the_chat_alone(
    chat_id: str, ran: list[RunCall], run: wake_turn_scheduler.WakeTurnRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(wake_turn_scheduler, "_MAX_WAIT_SECONDS", 0.05)
    gateway = get_agent_gateway()
    gateway.reserve_session(chat_id, active_message_id="user-turn")

    schedule_wake_turn(chat_id, run)
    await settle()

    assert ran == []
    assert gateway.get_active_message_id(chat_id) == "user-turn"
    assert chat_id not in wake_turn_scheduler._waiting
    # The next settlement may queue again.
    schedule_wake_turn(chat_id, run)
    assert chat_id in wake_turn_scheduler._waiting
    gateway.release_session(chat_id)
    await settle()
    assert len(ran) == 1


@pytest.mark.asyncio
async def test_a_draining_application_starts_no_wake(
    chat_id: str, ran: list[RunCall], run: wake_turn_scheduler.WakeTurnRunner
) -> None:
    gateway = get_agent_gateway()
    gateway._draining = True
    try:
        schedule_wake_turn(chat_id, run)
        await settle()
    finally:
        gateway._draining = False

    assert ran == []
    assert chat_id not in wake_turn_scheduler._waiting


@pytest.mark.asyncio
async def test_a_failing_wake_turn_gives_the_chat_back(
    chat_id: str, ran: list[RunCall], run: wake_turn_scheduler.WakeTurnRunner
) -> None:
    async def failing_run(*_args: object) -> None:
        raise RuntimeError("boom")

    schedule_wake_turn(chat_id, failing_run)
    await settle()

    assert not get_agent_gateway().is_session_active(chat_id)
    assert chat_id not in wake_turn_scheduler._waiting
    schedule_wake_turn(chat_id, run)
    await settle()
    assert len(ran) == 1


class _IMTurns:
    """A probe that reports the chats whose member is mid-conversation in an IM channel."""

    def __init__(self, busy: set[str]) -> None:
        self.busy = busy

    def is_busy(self, chat_id: str) -> bool:
        return chat_id in self.busy


@pytest.fixture
def im_turns() -> Iterator[_IMTurns]:
    probe = _IMTurns(set())
    set_chat_busy_probe(probe)
    yield probe
    set_chat_busy_probe(None)


@pytest.mark.asyncio
async def test_a_chat_the_member_is_talking_in_over_im_is_woken_only_after_that_turn_ends(
    chat_id: str, ran: list[RunCall], run: wake_turn_scheduler.WakeTurnRunner, im_turns: _IMTurns
) -> None:
    # The IM turn is not a gateway turn: the gateway sees the chat as free the whole time.
    im_turns.busy.add(chat_id)
    assert not get_agent_gateway().is_session_active(chat_id)

    schedule_wake_turn(chat_id, run)
    await asyncio.sleep(0.1)
    assert ran == []

    im_turns.busy.discard(chat_id)
    await settle()

    assert len(ran) == 1


@pytest.mark.asyncio
async def test_a_chat_the_probe_does_not_report_is_not_delayed(
    chat_id: str, ran: list[RunCall], run: wake_turn_scheduler.WakeTurnRunner, im_turns: _IMTurns
) -> None:
    im_turns.busy.add("another-chat")

    schedule_wake_turn(chat_id, run)
    await settle()

    assert len(ran) == 1
