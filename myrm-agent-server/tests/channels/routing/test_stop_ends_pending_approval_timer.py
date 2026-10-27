"""Ending a session that waits on a tool approval also ends the approval's timeout guard.

Runs on the real ``AgentRouter`` and the real ``ApprovalTimeoutScheduler``: a timer left behind would resume the
session the user just ended and answer the approval on their behalf.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Iterator
from unittest.mock import AsyncMock, MagicMock

import pytest
from myrm_agent_harness.agent.middlewares.approval.scheduler import ApprovalTimeoutScheduler
from myrm_agent_harness.utils.runtime.cancellation import CancellationToken

from app.channels.routing.router import AgentRouter
from app.channels.routing.router_models import _ActiveTask, _AgentTurnScratch, _RouterExecutionContext
from app.channels.types import InboundMessage, ProgressUpdate, QuickReply, StreamingText

_CHAT_KEY = "telegram:c1"
_TIMER_SECONDS = 0.05
_APPROVE = ProgressUpdate(
    label="shell needs approval: run the build",
    quick_replies=(QuickReply(label="Approve", text="/approve", required=True),),
)


@pytest.fixture(autouse=True)
def _scheduler() -> Iterator[ApprovalTimeoutScheduler]:
    scheduler = ApprovalTimeoutScheduler.get()
    scheduler.cancel_all()
    yield scheduler
    scheduler.cancel_all()


def _inbound(content: str = "/stop", *, thread_id: str | None = None) -> InboundMessage:
    return InboundMessage(
        channel="telegram",
        sender_id="u1",
        chat_id="c1",
        content=content,
        thread_id=thread_id,
        metadata={"locale": "en"},
    )


def _router(stream: object | None = None) -> tuple[AgentRouter, MagicMock]:
    bus = MagicMock()
    bus.consume_inbound = AsyncMock(side_effect=TimeoutError)
    bus.publish_outbound = AsyncMock()
    bus.edit_channel_message = AsyncMock()
    bus.send_tracked = AsyncMock(return_value="prompt-1")
    bus.get_channel = MagicMock(return_value=None)
    executor = MagicMock()
    executor.execute_stream = stream
    router = AgentRouter(bus=bus, pairing_store=MagicMock(), agent_executor=executor)
    router._resolve_mobile_status_deep_link = AsyncMock(return_value=None)  # type: ignore[method-assign]
    return router, bus


def _entry() -> _ActiveTask:
    return _ActiveTask(
        task=asyncio.create_task(asyncio.Event().wait()),  # type: ignore[arg-type]
        cancel_token=CancellationToken(),
        channel="telegram",
        chat_id="c1",
        placeholder_id=None,
        started_at=0.0,
        requester_id="u1",
    )


def _arm_timer(scheduler: ApprovalTimeoutScheduler) -> AsyncMock:
    """Arm the chat's approval timer the way the channel executor does: one key per chat, no topic."""
    resumed = AsyncMock()
    scheduler.schedule(_CHAT_KEY, _TIMER_SECONDS, "deny", resumed)
    return resumed


async def _let_a_timer_fire() -> None:
    await asyncio.sleep(_TIMER_SECONDS * 4)


@pytest.mark.asyncio
async def test_stop_ends_the_timer_of_the_approval_the_chat_was_waiting_on(_scheduler: ApprovalTimeoutScheduler) -> None:
    router, _bus = _router()
    router._active_tasks[_CHAT_KEY] = _entry()
    router._approval_msg_ids[_CHAT_KEY] = "card-1"
    resumed = _arm_timer(_scheduler)

    await router._cancel_active_task(_inbound())
    await _let_a_timer_fire()

    resumed.assert_not_awaited()
    assert _scheduler.pending_count == 0


@pytest.mark.asyncio
async def test_stop_ends_the_timer_of_a_turn_that_ended_at_an_approval_request(_scheduler: ApprovalTimeoutScheduler) -> None:
    """The router itself keeps the turn's entry and approval marker once its stream ends at the request."""

    async def stream(*_a: object, **_k: object) -> AsyncGenerator[object, None]:
        yield StreamingText(text="checking the build")
        yield _APPROVE

    router, _bus = _router(stream)
    ctx = _RouterExecutionContext(
        user_id="u1", state_key=_CHAT_KEY, chat_id="c1", message_id="m1", topic_ctx=None, exec_msg=_inbound("build it")
    )
    # The router runs a turn in its own task, and that is the task a stop cancels.
    turn = asyncio.create_task(
        router._execute_prepared_context(ctx, _AgentTurnScratch(), is_resume=False, inbound_had_voice=False)
    )
    await turn
    assert _CHAT_KEY in router._active_tasks
    assert router._approval_msg_ids == {_CHAT_KEY: "prompt-1"}
    resumed = _arm_timer(_scheduler)

    await router._cancel_active_task(_inbound())
    await _let_a_timer_fire()

    resumed.assert_not_awaited()
    assert _scheduler.pending_count == 0


@pytest.mark.asyncio
async def test_a_new_session_ends_the_timer_of_the_approval_the_old_one_was_waiting_on(
    _scheduler: ApprovalTimeoutScheduler,
) -> None:
    router, _bus = _router()
    router._active_tasks[_CHAT_KEY] = _entry()
    router._approval_msg_ids[_CHAT_KEY] = "card-1"
    resumed = _arm_timer(_scheduler)

    assert await router._abort_session_task(_CHAT_KEY, reason="New session") is True
    await _let_a_timer_fire()

    resumed.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("card_id", ["prompt-1", None])
async def test_stop_ends_the_timer_of_a_delegated_runs_approval(
    _scheduler: ApprovalTimeoutScheduler, card_id: str | None
) -> None:
    async def stream(*_a: object, **_k: object) -> AsyncGenerator[object, None]:
        yield StreamingText(text="refactoring")
        yield _APPROVE

    router, bus = _router(stream)
    bus.send_tracked = AsyncMock(return_value=card_id)
    await router._handle_delegation_inbound(_inbound("/delegate x"), "x")
    for _ in range(300):
        if _CHAT_KEY in router._approval_msg_ids:
            break
        await asyncio.sleep(0.01)
    assert _CHAT_KEY in router._approval_msg_ids
    resumed = _arm_timer(_scheduler)

    await router._cancel_active_task(_inbound())
    await _let_a_timer_fire()

    resumed.assert_not_awaited()
    assert _scheduler.pending_count == 0


@pytest.mark.asyncio
async def test_stopping_one_topic_leaves_the_approval_timer_of_another_topic(_scheduler: ApprovalTimeoutScheduler) -> None:
    """The timer is keyed by the chat, not the topic; only the topic whose own session waits may end it."""
    router, _bus = _router()
    router._active_tasks[f"{_CHAT_KEY}:t1"] = _entry()
    router._approval_msg_ids[f"{_CHAT_KEY}:t1"] = "card-1"
    router._active_tasks[f"{_CHAT_KEY}:t2"] = _entry()
    resumed = _arm_timer(_scheduler)

    await router._cancel_active_task(_inbound(thread_id="t2"))
    assert _scheduler.pending_count == 1

    await router._cancel_active_task(_inbound(thread_id="t1"))
    await _let_a_timer_fire()

    resumed.assert_not_awaited()
    assert _scheduler.pending_count == 0


@pytest.mark.asyncio
async def test_stopping_a_turn_that_was_not_waiting_on_an_approval_leaves_the_chats_timer(
    _scheduler: ApprovalTimeoutScheduler,
) -> None:
    router, _bus = _router()
    router._active_tasks[_CHAT_KEY] = _entry()
    resumed = _arm_timer(_scheduler)

    await router._cancel_active_task(_inbound())
    await _let_a_timer_fire()

    resumed.assert_awaited_once()
