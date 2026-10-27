"""A delegated run can be stopped: by its user through /stop, and by the reaper once it runs past its limit.

Both stop the run the way the router stops a foreground turn: the cancellation token for a run that checks
it, the asyncio task for one that never does (a hung tool). Stopping must free everything the run held.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator

import pytest

from app.channels.delegation import DelegationCoordinator, DelegationStatus, DelegationTask, build_delegation_task
from app.channels.types import InboundMessage, OutboundMessage, ProgressUpdate, StreamingText


class _Bus:
    def __init__(self) -> None:
        self.published: list[OutboundMessage] = []

    async def publish_outbound(self, message: OutboundMessage) -> None:
        self.published.append(message)


class _HungExecutor:
    """Streams one snapshot, then waits forever and never looks at its cancellation token."""

    def execute_stream(self, *_args: object, **_kwargs: object) -> AsyncGenerator[object, None]:
        return self._stream()

    async def _stream(self) -> AsyncGenerator[object, None]:
        yield StreamingText(text="working")
        await asyncio.Event().wait()


class _StopAwareExecutor:
    """Treats a cancellation as the end of its stream and returns what it has so far, as an executor that catches it would."""

    def execute_stream(self, *_args: object, **_kwargs: object) -> AsyncGenerator[object, None]:
        return self._stream()

    async def _stream(self) -> AsyncGenerator[object, None]:
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            yield OutboundMessage(channel="telegram", recipient_id="chat-1", user_id="user-1", content="half an answer")


async def _no_hand_over(_request: ProgressUpdate) -> None:
    raise AssertionError("a run that never reached an approval must not hand one over")


def _inbound() -> InboundMessage:
    return InboundMessage(
        channel="telegram", sender_id="user-1", chat_id="chat-1", content="x", user_id="user-1", metadata={"locale": "en"}
    )


async def _start(
    coordinator: DelegationCoordinator,
    bus: _Bus,
    *,
    user: str = "user-1",
    chat: str = "chat-1",
    executor: object | None = None,
) -> tuple[DelegationTask, asyncio.Task[None]]:
    task = build_delegation_task(origin_channel="telegram", origin_user_id=user, origin_chat_id=chat, prompt="do the report")
    coordinator.register_task(task)
    runner = asyncio.create_task(
        coordinator.execute_task_lifecycle(
            task,
            executor or _HungExecutor(),  # type: ignore[arg-type]
            bus,  # type: ignore[arg-type]
            _inbound(),
            hand_over_approval=_no_hand_over,
        )
    )
    for _ in range(50):
        if task.status is DelegationStatus.RUNNING:
            break
        await asyncio.sleep(0)
    await asyncio.sleep(0)
    return task, runner


async def _finish(runner: asyncio.Task[None]) -> None:
    with pytest.raises(asyncio.CancelledError):
        await runner


@pytest.mark.asyncio
async def test_stopping_cancels_a_run_that_ignores_its_token_and_leaves_nothing_behind() -> None:
    coordinator, bus = DelegationCoordinator(), _Bus()
    task, runner = await _start(coordinator, bus)
    token = coordinator.get_cancellation_token(task.task_id)
    assert token is not None

    assert coordinator.cancel_for_chat("telegram", "chat-1", "user-1") == [task.task_id]
    await _finish(runner)

    assert task.status is DelegationStatus.CANCELLED
    assert task.completed_at is not None
    assert token.is_cancelled
    assert bus.published == []  # /stop answers the user itself; the lifecycle adds no second message
    assert coordinator.get_task(task.task_id) is None
    assert coordinator.find_active_task("telegram", "user-1") is None


@pytest.mark.asyncio
async def test_stopping_reaches_only_the_running_tasks_of_that_user_in_that_chat() -> None:
    coordinator, bus = DelegationCoordinator(), _Bus()
    mine, mine_runner = await _start(coordinator, bus)
    other_user, other_user_runner = await _start(coordinator, bus, user="user-2")
    other_chat, other_chat_runner = await _start(coordinator, bus, chat="chat-2")

    assert coordinator.cancel_for_chat("telegram", "chat-1", "user-1") == [mine.task_id]
    await _finish(mine_runner)
    assert coordinator.cancel_for_chat("telegram", "chat-1", "user-1") == []
    assert coordinator.cancel_for_chat("whatsapp", "chat-1", "user-1") == []

    assert other_user.status is DelegationStatus.RUNNING
    assert other_chat.status is DelegationStatus.RUNNING
    for runner in (other_user_runner, other_chat_runner):
        runner.cancel()
        await _finish(runner)


@pytest.mark.asyncio
async def test_the_reaper_cancels_a_hung_run_and_tells_the_chat_why() -> None:
    coordinator, bus = DelegationCoordinator(), _Bus()
    task, runner = await _start(coordinator, bus)
    task.started_at = 1.0

    assert coordinator.reap_stale_tasks() == [task.task_id]
    await _finish(runner)

    assert task.status is DelegationStatus.TIMED_OUT
    assert [m.content for m in bus.published] == [
        f"⏱ **Background task stopped** `[{task.task_id}]` · it ran past the 60-minute limit."
    ]
    assert bus.published[0].recipient_id == "chat-1"
    assert coordinator.get_task(task.task_id) is None


@pytest.mark.asyncio
async def test_a_run_cancelled_from_outside_ends_cancelled_without_a_message() -> None:
    coordinator, bus = DelegationCoordinator(), _Bus()
    task, runner = await _start(coordinator, bus)

    runner.cancel()
    await _finish(runner)

    assert task.status is DelegationStatus.CANCELLED
    assert bus.published == []
    assert coordinator.get_task(task.task_id) is None


@pytest.mark.asyncio
async def test_a_stopped_run_that_ends_its_stream_gracefully_still_delivers_nothing() -> None:
    coordinator, bus = DelegationCoordinator(), _Bus()
    task, runner = await _start(coordinator, bus, executor=_StopAwareExecutor())

    assert coordinator.cancel_for_chat("telegram", "chat-1", "user-1") == [task.task_id]
    await runner  # the stream ended on its own: the lifecycle returns instead of re-raising

    assert task.status is DelegationStatus.CANCELLED
    assert bus.published == []  # the half answer is not reported as a finished task
    assert coordinator.get_task(task.task_id) is None


@pytest.mark.asyncio
async def test_a_reaped_run_that_ends_its_stream_gracefully_delivers_only_the_timeout_notice() -> None:
    coordinator, bus = DelegationCoordinator(), _Bus()
    task, runner = await _start(coordinator, bus, executor=_StopAwareExecutor())
    task.started_at = 1.0

    assert coordinator.reap_stale_tasks() == [task.task_id]
    await runner

    assert task.status is DelegationStatus.TIMED_OUT
    assert [m.content for m in bus.published] == [
        f"⏱ **Background task stopped** `[{task.task_id}]` · it ran past the 60-minute limit."
    ]
