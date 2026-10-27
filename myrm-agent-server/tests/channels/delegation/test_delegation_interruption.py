"""A delegated task cut short by the service stopping tells its chat, in the sender's language and thread.

Runs on the real ``AgentRouter`` and ``DelegationCoordinator`` with a stub executor: the notice is what the chat is
sent while the channels are still up, so the user knows to send the request again instead of waiting for a result
that will never come.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from unittest.mock import MagicMock

import pytest

from app.channels.delegation import DelegationStatus
from app.channels.i18n import get_text
from app.channels.routing.router import AgentRouter
from app.channels.types import InboundMessage, OutboundMessage, StreamingText
from tests.channels.delegation.test_delegation_router_control import _delegate, _hang, _inbound, _router, _running, _said, _until


def _notices(bus: MagicMock) -> list[str]:
    """The English interruption notices the chat was sent, one per task."""
    return [text for text in _said(bus) if "Background task interrupted" in text]


def _localized(locale: str, *, thread_id: str | None = None) -> InboundMessage:
    return InboundMessage(
        channel="telegram",
        sender_id="u1",
        chat_id="c1",
        content="/delegate x",
        thread_id=thread_id,
        metadata={"locale": locale},
    )


async def _delegate_as(router: AgentRouter, msg: InboundMessage) -> str:
    await router._handle_delegation_inbound(msg, "x")
    task_id = next(reversed(router._delegation_coordinator._tasks))
    await _until(lambda: router._delegation_coordinator._tasks[task_id].status is DelegationStatus.RUNNING)
    return task_id


@pytest.mark.asyncio
@pytest.mark.parametrize("locale", ["en", "ja", "zh-CN"])
async def test_stopping_the_router_tells_each_chat_its_task_was_interrupted_in_its_language(locale: str) -> None:
    router, bus = _router(_hang)
    task_id = await _delegate_as(router, _localized(locale))

    await router.stop()

    notice = _said(bus)[-1]
    assert notice == get_text(_localized(locale), "delegation_interrupted", task_id=task_id)
    assert task_id in notice


@pytest.mark.asyncio
async def test_the_notice_goes_to_the_chat_and_topic_the_task_came_from() -> None:
    router, bus = _router(_hang)
    await _delegate_as(router, _localized("en", thread_id="topic-9"))

    await router.stop()

    notice = bus.publish_outbound.call_args_list[-1].args[0]
    assert isinstance(notice, OutboundMessage)
    assert (notice.recipient_id, notice.thread_id) == ("c1", "topic-9")


@pytest.mark.asyncio
async def test_every_running_task_is_told_and_leaves_nothing_behind() -> None:
    router, bus = _router(_hang)
    for prompt in ("one", "two"):
        await _delegate(router, prompt)
    await _until(lambda: _running(router) == 2)

    await router.stop()

    assert len(_notices(bus)) == 2
    assert not router._delegation_coordinator._tasks
    assert router._delegation_guard.can_accept("telegram", "u1")


@pytest.mark.asyncio
async def test_a_task_the_user_just_stopped_is_not_told_again() -> None:
    router, bus = _router(_hang)
    await _delegate(router)
    await _until(lambda: _running(router) == 1)
    await router._cancel_active_task(_inbound("/stop"))
    assert router._delegation_coordinator._tasks  # the run has not settled yet

    await router.stop()

    assert _notices(bus) == []


@pytest.mark.asyncio
async def test_a_task_that_finished_before_the_stop_is_not_told() -> None:
    async def quick(*_a: object, **_k: object) -> AsyncGenerator[object, None]:
        yield OutboundMessage(channel="telegram", recipient_id="c1", content="the report", user_id="u1")

    router, bus = _router(quick)
    await _delegate(router)
    await _until(lambda: not router._delegation_coordinator._tasks)

    await router.stop()

    assert _notices(bus) == []
    assert any("the report" in text for text in _said(bus))


@pytest.mark.asyncio
async def test_a_task_the_time_limit_just_ended_is_not_told_twice() -> None:
    router, bus = _router(_hang)
    await _delegate(router)
    await _until(lambda: _running(router) == 1)
    for task in router._delegation_coordinator._tasks.values():
        task.started_at = 1.0
    router._delegation_coordinator.reap_stale_tasks()
    assert router._delegation_coordinator._tasks  # the run has not settled yet

    await router.stop()

    await _until(lambda: not router._delegation_coordinator._tasks)
    assert _notices(bus) == []
    assert sum("Background task stopped" in text for text in _said(bus)) == 1


@pytest.mark.asyncio
async def test_the_run_still_cleans_up_after_itself() -> None:
    cleaned = asyncio.Event()

    async def stream(*_a: object, **_k: object) -> AsyncGenerator[object, None]:
        try:
            yield StreamingText(text="working")
            await asyncio.Event().wait()
        finally:
            cleaned.set()

    router, _bus = _router(stream)
    await _delegate(router)
    await _until(lambda: _running(router) == 1)

    await router.stop()

    assert cleaned.is_set()


@pytest.mark.asyncio
async def test_a_run_that_will_not_stop_cannot_hold_the_shutdown() -> None:
    release = asyncio.Event()

    async def stubborn(*_a: object, **_k: object) -> AsyncGenerator[object, None]:
        yield StreamingText(text="working")
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            await release.wait()
            raise

    router, _bus = _router(stubborn)
    await _delegate(router)
    await _until(lambda: _running(router) == 1)

    interrupted = await asyncio.wait_for(router._delegation_coordinator.interrupt_all(grace_seconds=0.05), timeout=2)

    assert len(interrupted) == 1
    release.set()
    await _until(lambda: not router._delegation_coordinator._tasks)


@pytest.mark.asyncio
async def test_a_notice_that_cannot_be_sent_does_not_fail_the_shutdown() -> None:
    router, bus = _router(_hang)
    await _delegate(router)
    await _until(lambda: _running(router) == 1)
    bus.publish_outbound.side_effect = ConnectionError("channel already gone")

    await router.stop()

    assert not router._delegation_coordinator._tasks
    assert router._delegation_guard.can_accept("telegram", "u1")
