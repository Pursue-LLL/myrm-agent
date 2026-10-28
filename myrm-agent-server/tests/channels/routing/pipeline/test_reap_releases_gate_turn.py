"""The stuck-task watchdog frees the chat by the SessionGate session and turn its task ran as.

Runs on the real ``AgentRouter`` and the real ``SessionGate``. The gate session of a direct message is keyed by its
sender and the router's task registry by its chat, so only the key recorded when the task started names the session the
watchdog must release; a turn that ignores its cancellation is freed by that release alone.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncGenerator, AsyncIterator, Callable
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.channels.routing.router import AgentRouter
from app.channels.routing.router_constants import _STUCK_TASK_TIMEOUT
from app.channels.routing.router_models import _ActiveTask, _AgentTurnScratch, _RouterExecutionContext
from app.channels.routing.session_gate import SessionGate, SessionGateConfig
from app.channels.types import InboundMessage

_STATE_KEY = "telegram:chat-9"
_GATE_KEY = "telegram:u1"


def _dm(text: str) -> InboundMessage:
    return InboundMessage(channel="telegram", sender_id="u1", chat_id="chat-9", content=text, metadata={"locale": "en"})


class _Harness:
    """A real router whose gate hands each turn to a runner; the turn named ``stuck`` runs the router's real execute step."""

    def __init__(self, *, ignores_cancellation: bool) -> None:
        self.ran: list[str] = []
        self.registered: _ActiveTask | None = None
        self.unstick = asyncio.Event()
        self.finish_waiting = asyncio.Event()
        self._ignores_cancellation = ignores_cancellation
        bus = MagicMock()
        bus.consume_inbound = AsyncMock(side_effect=TimeoutError)
        bus.publish_outbound = AsyncMock()
        bus.get_channel = MagicMock(return_value=None)
        executor = MagicMock()
        executor.execute_stream = self._stream
        self.router = AgentRouter(bus=bus, pairing_store=MagicMock(), agent_executor=executor)
        self.router._resolve_mobile_status_deep_link = AsyncMock(return_value=None)  # type: ignore[method-assign]
        self.gate = SessionGate(SessionGateConfig(debounce_window_ms=0, max_pending_per_session=10), on_ready=self._run)
        self.router._gate = self.gate

    async def _stream(self, *_args: object, **_kwargs: object) -> AsyncGenerator[object, None]:
        self.registered = self.router._active_tasks.get(_STATE_KEY)
        while not self.unstick.is_set():
            try:
                await self.unstick.wait()
            except asyncio.CancelledError:
                if not self._ignores_cancellation:
                    raise
        return
        yield

    async def _run(self, msg: InboundMessage) -> None:
        self.ran.append(msg.content)
        if msg.content == "waiting":
            await self.finish_waiting.wait()
        if msg.content != "stuck":
            return
        ctx = _RouterExecutionContext(
            user_id="u1", state_key=_STATE_KEY, chat_id="chat-9", message_id="m1", topic_ctx=None, exec_msg=msg
        )
        await self.router._execute_prepared_context(ctx, _AgentTurnScratch(), is_resume=False, inbound_had_voice=False)

    async def reap_after_the_timeout(self) -> None:
        await self.router._reap_stuck_tasks(time.monotonic() + _STUCK_TASK_TIMEOUT + 10)


@pytest.fixture
async def make_harness() -> AsyncIterator[Callable[[bool], _Harness]]:
    """Builds harnesses and unsticks them at the end, so a failing assertion cannot leave a task that ignores its cancellation."""
    made: list[_Harness] = []

    def make(ignores_cancellation: bool) -> _Harness:
        harness = _Harness(ignores_cancellation=ignores_cancellation)
        made.append(harness)
        return harness

    yield make
    for harness in made:
        harness.unstick.set()
        harness.finish_waiting.set()
    await asyncio.sleep(0.1)


@pytest.mark.asyncio
async def test_a_running_task_records_the_gate_session_and_turn_it_ran_as(make_harness: Callable[[bool], _Harness]) -> None:
    harness = make_harness(False)
    harness.gate.submit(_dm("stuck"))
    await asyncio.sleep(0.1)

    entry = harness.registered
    assert entry is not None
    assert entry.gate_key == _GATE_KEY != _STATE_KEY
    assert entry.gate_turn == harness.gate.running_turn(_GATE_KEY) > 0


@pytest.mark.asyncio
async def test_a_turn_that_ignores_its_cancellation_is_freed_by_the_watchdog_release(
    make_harness: Callable[[bool], _Harness],
) -> None:
    harness = make_harness(True)
    harness.gate.submit(_dm("stuck"))
    await asyncio.sleep(0.1)
    harness.gate.submit(_dm("waiting"))
    await asyncio.sleep(0.1)
    assert harness.ran == ["stuck"]

    await harness.reap_after_the_timeout()
    await asyncio.sleep(0.1)

    assert harness.ran == ["stuck", "waiting"]


@pytest.mark.asyncio
async def test_the_late_unwinding_of_a_reaped_turn_does_not_end_the_turn_that_took_over(
    make_harness: Callable[[bool], _Harness],
) -> None:
    harness = make_harness(True)
    harness.gate.submit(_dm("stuck"))
    await asyncio.sleep(0.1)
    harness.gate.submit(_dm("waiting"))
    await harness.reap_after_the_timeout()
    await asyncio.sleep(0.1)
    took_over = harness.gate.running_turn(_GATE_KEY)
    assert harness.ran == ["stuck", "waiting"]

    harness.unstick.set()  # the reaped turn now unwinds and signals its own, long past, end
    await asyncio.sleep(0.1)
    harness.gate.submit(_dm("later"))
    await asyncio.sleep(0.1)

    assert harness.gate.running_turn(_GATE_KEY) == took_over
    assert harness.ran == ["stuck", "waiting"]
    harness.finish_waiting.set()
    await asyncio.sleep(0.1)
    assert harness.ran == ["stuck", "waiting", "later"]
