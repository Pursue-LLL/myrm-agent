"""A delegated task reports what really happened: the final reply, a failed turn as failed, never raw errors.

The coordinator consumes ``ChannelAgentExecutor.execute_stream``: ``StreamingText`` events are cumulative
snapshots, the last ``OutboundMessage`` is the authoritative reply, and a failed turn is an ordinary
reply flagged with ``metadata["error_type"]`` (see ``test_execute_finalize_errors``).
"""

from __future__ import annotations

import logging
import re
from collections.abc import AsyncGenerator, Callable

import pytest

from app.channels.delegation import DelegationCoordinator, DelegationStatus, DelegationTask, build_delegation_task
from app.channels.types import InboundMessage, OutboundMessage, StreamingText

_REF = re.compile(r"\[ref: ([0-9a-f]{8})\]")
_RAW_ERROR = "Sandbox container out of memory: /var/lib/sandbox/secret-token-42"
_SAFE_FAILURE = "Service temporarily unavailable due to a configuration issue. Please contact the administrator. [ref: deadbeef]"

StreamFactory = Callable[[DelegationCoordinator, DelegationTask], AsyncGenerator[object, None]]


class _Bus:
    def __init__(self) -> None:
        self.published: list[OutboundMessage] = []

    async def publish_outbound(self, message: OutboundMessage) -> None:
        self.published.append(message)


class _Executor:
    def __init__(self, stream: StreamFactory, coordinator: DelegationCoordinator, task: DelegationTask) -> None:
        self._stream = stream
        self._coordinator = coordinator
        self._task = task

    def execute_stream(self, *_args: object, **_kwargs: object) -> AsyncGenerator[object, None]:
        return self._stream(self._coordinator, self._task)


def _reply(content: str, *, error_type: str | None = None) -> OutboundMessage:
    return OutboundMessage(
        channel="telegram",
        recipient_id="chat-1",
        user_id="user-1",
        content=content,
        metadata={"error_type": error_type} if error_type else None,
    )


async def _run(stream: StreamFactory) -> tuple[DelegationTask, str]:
    coordinator = DelegationCoordinator()
    task = build_delegation_task(
        origin_channel="telegram",
        origin_user_id="user-1",
        origin_chat_id="chat-1",
        raw_prompt="do the report",
        normalized_prompt="do the report",
    )
    coordinator.register_task(task)
    bus = _Bus()
    inbound = InboundMessage(channel="telegram", sender_id="user-1", chat_id="chat-1", content="do the report", user_id="user-1")

    await coordinator.execute_task_lifecycle(task, _Executor(stream, coordinator, task), bus, inbound)  # type: ignore[arg-type]

    assert len(bus.published) == 1
    return task, bus.published[0].content


@pytest.mark.asyncio
async def test_summary_is_the_final_reply_not_the_concatenated_snapshots() -> None:
    async def stream(_c: DelegationCoordinator, _t: DelegationTask) -> AsyncGenerator[object, None]:
        yield StreamingText(text="Hello")
        yield StreamingText(text="Hello world")
        yield _reply("Hello world")

    task, card = await _run(stream)

    assert task.status == DelegationStatus.COMPLETED
    assert task.result_summary == "Hello world"
    assert card.count("Hello world") == 1
    assert "✅" in card
    assert "执行完成" in card


@pytest.mark.asyncio
async def test_summary_falls_back_to_the_last_snapshot_without_a_final_reply() -> None:
    async def stream(_c: DelegationCoordinator, _t: DelegationTask) -> AsyncGenerator[object, None]:
        yield StreamingText(text="Hel")
        yield StreamingText(text="Hello world")

    task, _card = await _run(stream)

    assert task.status == DelegationStatus.COMPLETED
    assert task.result_summary == "Hello world"


@pytest.mark.asyncio
async def test_silent_run_keeps_the_generic_success_summary() -> None:
    async def stream(_c: DelegationCoordinator, _t: DelegationTask) -> AsyncGenerator[object, None]:
        if False:
            yield None

    task, _card = await _run(stream)

    assert task.status == DelegationStatus.COMPLETED
    assert task.result_summary == "Task finished successfully."


@pytest.mark.asyncio
async def test_failed_turn_reply_marks_the_task_failed_with_the_member_safe_text() -> None:
    async def stream(_c: DelegationCoordinator, _t: DelegationTask) -> AsyncGenerator[object, None]:
        yield _reply(_SAFE_FAILURE, error_type="billing")

    task, card = await _run(stream)

    assert task.status == DelegationStatus.FAILED
    assert task.error_message == _SAFE_FAILURE
    assert task.result_summary == ""
    assert "❌" in card
    assert "执行失败" in card
    assert _SAFE_FAILURE in card
    assert "执行完成" not in card
    assert "Task finished successfully." not in card


@pytest.mark.asyncio
async def test_executor_exception_never_reaches_the_chat_and_is_logged_under_the_reference(
    caplog: pytest.LogCaptureFixture,
) -> None:
    async def stream(_c: DelegationCoordinator, _t: DelegationTask) -> AsyncGenerator[object, None]:
        if False:
            yield None
        raise RuntimeError(_RAW_ERROR)

    with caplog.at_level(logging.ERROR):
        task, card = await _run(stream)

    assert task.status == DelegationStatus.FAILED
    assert "执行失败" in card
    for text in (task.error_message, card):
        assert "secret-token-42" not in text
        assert "Sandbox container" not in text
    ref = _REF.search(card)
    assert ref is not None
    assert ref.group(1) in task.error_message
    logged = [r.getMessage() for r in caplog.records if "secret-token-42" in r.getMessage()]
    assert len(logged) == 1
    assert f"[ref: {ref.group(1)}]" in logged[0]


@pytest.mark.asyncio
async def test_a_task_failed_while_running_stays_failed() -> None:
    """The stale-task reaper fails a task and cancels its stream; the stream's end must not turn it into a success."""

    async def stream(coordinator: DelegationCoordinator, task: DelegationTask) -> AsyncGenerator[object, None]:
        coordinator.update_task_status(task.task_id, DelegationStatus.FAILED, error_message="Task timed out after 3601 seconds")
        yield _reply("partial answer")

    task, card = await _run(stream)

    assert task.status == DelegationStatus.FAILED
    assert task.error_message == "Task timed out after 3601 seconds"
    assert task.result_summary == ""
    assert "❌" in card
    assert "执行失败" in card
    assert "Task timed out after 3601 seconds" in card


@pytest.mark.asyncio
async def test_a_cancelled_task_stays_cancelled() -> None:
    async def stream(coordinator: DelegationCoordinator, task: DelegationTask) -> AsyncGenerator[object, None]:
        assert coordinator.cancel_task(task.task_id)
        yield _reply("partial answer")

    task, card = await _run(stream)

    assert task.status == DelegationStatus.CANCELLED
    assert task.result_summary == ""
    assert "已取消" in card
    assert "执行完成" not in card
