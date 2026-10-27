"""A delegated task stays under the chat's control: its tool approvals reach the chat, /stop ends it, a hung run is freed.

Runs on the real ``AgentRouter`` with a stub executor, so the chat-side state (pending-approval entry, quota guard,
replies) is the production one.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Callable
from unittest.mock import AsyncMock, MagicMock

import pytest
from myrm_agent_harness.utils.runtime.cancellation import CancellationToken

from app.channels.delegation import DelegationStatus
from app.channels.i18n import get_text
from app.channels.routing.router import AgentRouter
from app.channels.routing.router_models import _ActiveTask
from app.channels.types import InboundMessage, ProgressUpdate, QuickReply, StreamingText

_STATE_KEY = "telegram:c1"
_APPROVE = ProgressUpdate(
    label="shell needs approval: run the build\n⏱ Timeout: 120s (auto-deny)",
    quick_replies=(
        QuickReply(label="Approve", text="/approve", required=True),
        QuickReply(label="Deny", text="/deny", required=True),
    ),
)

Stream = Callable[..., AsyncGenerator[object, None]]


def _inbound(content: str = "/delegate x", *, user: str = "u1") -> InboundMessage:
    return InboundMessage(
        channel="telegram", sender_id=user, chat_id="c1", content=content, user_id=user, metadata={"locale": "en"}
    )


def _router(stream: Stream) -> tuple[AgentRouter, MagicMock]:
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
    router._gate.submit = MagicMock()  # type: ignore[method-assign]
    return router, bus


async def _until(condition: Callable[[], bool]) -> None:
    for _ in range(300):
        if condition():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("the condition never became true")


def _said(bus: MagicMock) -> list[str]:
    return [call.args[0].content for call in bus.publish_outbound.call_args_list]


async def _hang(*_args: object, **_kwargs: object) -> AsyncGenerator[object, None]:
    yield StreamingText(text="working")
    await asyncio.Event().wait()


async def _delegate(router: AgentRouter, prompt: str = "x") -> None:
    await router._handle_delegation_inbound(_inbound(), prompt)


def _running(router: AgentRouter) -> int:
    return sum(1 for t in router._delegation_coordinator._tasks.values() if t.status is DelegationStatus.RUNNING)


@pytest.mark.asyncio
async def test_a_delegated_approval_reaches_the_chat_and_the_chats_answer_resumes_the_run() -> None:
    async def stream(*_a: object, **_k: object) -> AsyncGenerator[object, None]:
        yield StreamingText(text="refactoring")
        yield _APPROVE

    router, bus = _router(stream)
    await _delegate(router)
    await _until(lambda: bus.send_tracked.call_count == 1)

    prompt = bus.send_tracked.call_args.args[0]
    assert prompt.content == _APPROVE.label
    assert [q.text for q in prompt.quick_replies] == ["/approve", "/deny"]
    entry = router._active_tasks[_STATE_KEY]
    assert entry.requester_id == "u1"
    assert entry.steering_token is None and entry.busy_input_mode is None
    assert router._approval_msg_ids == {_STATE_KEY: "prompt-1"}
    assert len(_said(bus)) == 1  # the receipt; the run has not finished, so no completion notice

    await router._handle_approval_command(_inbound("/approve"), "allow_once")

    resume = router._gate.submit.call_args.args[0]  # type: ignore[attr-defined]
    assert resume.resume_value["decisions"][0]["type"] == "approve"
    bus.edit_channel_message.assert_awaited_once()
    assert router._approval_msg_ids == {}


@pytest.mark.asyncio
async def test_a_turn_running_in_the_chat_keeps_its_entry_when_a_delegated_approval_arrives() -> None:
    async def stream(*_a: object, **_k: object) -> AsyncGenerator[object, None]:
        yield _APPROVE

    router, bus = _router(stream)
    turn = asyncio.create_task(asyncio.Event().wait())
    running = _ActiveTask(
        task=turn,  # type: ignore[arg-type]
        cancel_token=CancellationToken(),
        channel="telegram",
        chat_id="c1",
        placeholder_id=None,
        started_at=0.0,
        requester_id="u1",
    )
    router._active_tasks[_STATE_KEY] = running

    await _delegate(router)
    await _until(lambda: bus.send_tracked.call_count == 1)

    assert router._active_tasks[_STATE_KEY] is running
    assert router._approval_msg_ids == {_STATE_KEY: "prompt-1"}  # the turn's cleanup keeps its entry while this is set
    turn.cancel()


@pytest.mark.asyncio
async def test_a_newer_delegated_approval_replaces_the_entry_of_a_finished_turn() -> None:
    async def stream(*_a: object, **_k: object) -> AsyncGenerator[object, None]:
        yield _APPROVE

    router, bus = _router(stream)
    finished = asyncio.create_task(asyncio.sleep(0))
    await finished
    stale = _ActiveTask(
        task=finished,  # type: ignore[arg-type]
        cancel_token=CancellationToken(),
        channel="telegram",
        chat_id="c1",
        placeholder_id=None,
        started_at=0.0,
        requester_id="someone-else",
    )
    router._active_tasks[_STATE_KEY] = stale

    await _delegate(router)
    await _until(lambda: bus.send_tracked.call_count == 1)

    assert router._active_tasks[_STATE_KEY] is not stale
    assert router._active_tasks[_STATE_KEY].requester_id == "u1"


@pytest.mark.asyncio
async def test_stop_ends_a_delegated_task_and_frees_its_quota() -> None:
    router, bus = _router(_hang)
    await _delegate(router)
    await _until(lambda: _running(router) == 1)

    await router._cancel_active_task(_inbound("/stop"))

    assert _said(bus)[-1] == get_text(_inbound(), "execution_stopped")
    await _until(lambda: router._delegation_guard.can_accept("telegram", "u1") and not router._delegation_coordinator._tasks)
    assert len(_said(bus)) == 2  # the receipt and the /stop answer; no completion or failure notice follows


@pytest.mark.asyncio
async def test_stop_ends_the_chat_turn_first_and_the_background_task_with_the_next_stop() -> None:
    router, bus = _router(_hang)
    await _delegate(router)
    await _until(lambda: _running(router) == 1)
    token = CancellationToken()
    turn = asyncio.create_task(asyncio.Event().wait())
    router._active_tasks[_STATE_KEY] = _ActiveTask(
        task=turn,  # type: ignore[arg-type]
        cancel_token=token,
        channel="telegram",
        chat_id="c1",
        placeholder_id=None,
        started_at=0.0,
        requester_id="u1",
    )

    await router._cancel_active_task(_inbound("/stop"))
    await asyncio.sleep(0)
    assert token.is_cancelled and turn.cancelled()
    assert _running(router) == 1

    await router._cancel_active_task(_inbound("/stop"))
    await _until(lambda: _running(router) == 0)


@pytest.mark.asyncio
async def test_stop_from_another_sender_does_not_end_the_task() -> None:
    router, bus = _router(_hang)
    await _delegate(router)
    await _until(lambda: _running(router) == 1)

    await router._cancel_active_task(_inbound("/stop", user="u2"))

    assert _said(bus)[-1] == get_text(_inbound(), "no_active_task_to_stop")
    assert _running(router) == 1
    router._delegation_coordinator.cancel_for_chat("telegram", "c1", "u1")


@pytest.mark.asyncio
async def test_a_hung_delegated_task_is_reaped_and_frees_its_quota() -> None:
    router, bus = _router(_hang)
    for prompt in ("one", "two"):
        await _delegate(router, prompt)
    await _until(lambda: _running(router) == 2)
    assert router._delegation_guard.can_accept("telegram", "u1") is False
    for task in router._delegation_coordinator._tasks.values():
        task.started_at = 1.0

    assert len(router._delegation_coordinator.reap_stale_tasks()) == 2

    await _until(lambda: router._delegation_guard.can_accept("telegram", "u1"))
    await _until(lambda: sum("Background task stopped" in text for text in _said(bus)) == 2)
