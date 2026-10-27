"""A delegated task delivers what really happened: the executor's final reply, the right status, never raw errors.

The coordinator consumes ``ChannelAgentExecutor.execute_stream``: ``StreamingText`` events are cumulative
snapshots, the last ``OutboundMessage`` is the authoritative reply, and a failed turn is an ordinary
reply flagged with ``metadata["error_type"]`` (see ``test_execute_finalize_errors``). The delivered message
is that reply, under a one-line status header in the sender's language.
"""

from __future__ import annotations

import logging
import re
from collections.abc import AsyncGenerator, Callable
from types import SimpleNamespace

import pytest

from app.channels.delegation import DelegationCoordinator, DelegationStatus, DelegationTask, build_delegation_task
from app.channels.delegation import delegation_coordinator as coordinator_module
from app.channels.types import (
    InboundMessage,
    MediaAttachment,
    MediaType,
    OutboundMessage,
    ProgressUpdate,
    QuickReply,
    StreamingText,
)

_REF = re.compile(r"\[ref: ([0-9a-f]{8})\]")
_RAW_ERROR = "Sandbox container out of memory: /var/lib/sandbox/secret-token-42"
_SAFE_FAILURE = "Service temporarily unavailable due to a configuration issue. Please contact the administrator. [ref: deadbeef]"

StreamFactory = Callable[[DelegationCoordinator, DelegationTask], AsyncGenerator[object, None]]


class _Bus:
    def __init__(self) -> None:
        self.published: list[OutboundMessage] = []

    async def publish_outbound(self, message: OutboundMessage) -> None:
        self.published.append(message)


class _HandOver:
    """The router's approval hand-over: records what the coordinator hands to the chat."""

    def __init__(self, error: Exception | None = None) -> None:
        self.requests: list[ProgressUpdate] = []
        self._error = error

    async def __call__(self, request: ProgressUpdate) -> None:
        if self._error is not None:
            raise self._error
        self.requests.append(request)


class _Executor:
    def __init__(self, stream: StreamFactory, coordinator: DelegationCoordinator, task: DelegationTask) -> None:
        self._stream = stream
        self._coordinator = coordinator
        self._task = task

    def execute_stream(self, *_args: object, **_kwargs: object) -> AsyncGenerator[object, None]:
        return self._stream(self._coordinator, self._task)


def _reply(
    content: str,
    *,
    error_type: str | None = None,
    media: tuple[MediaAttachment, ...] = (),
    thread_id: str | None = None,
) -> OutboundMessage:
    return OutboundMessage(
        channel="telegram",
        recipient_id="chat-1",
        user_id="user-1",
        content=content,
        metadata={"error_type": error_type} if error_type else None,
        media=media,
        thread_id=thread_id,
    )


def _inbound(locale: str, thread_id: str | None) -> InboundMessage:
    return InboundMessage(
        channel="telegram",
        sender_id="user-1",
        chat_id="chat-1",
        content="do the report",
        user_id="user-1",
        thread_id=thread_id,
        metadata={"locale": locale},
    )


async def _run_lifecycle(
    stream: StreamFactory,
    *,
    locale: str = "en",
    thread_id: str | None = None,
    timeout_seconds: float = 3600.0,
    hand_over: _HandOver | None = None,
) -> tuple[DelegationCoordinator, DelegationTask, list[OutboundMessage]]:
    coordinator = DelegationCoordinator()
    task = build_delegation_task(
        origin_channel="telegram",
        origin_user_id="user-1",
        origin_chat_id="chat-1",
        prompt="do the report",
        timeout_seconds=timeout_seconds,
    )
    coordinator.register_task(task)
    bus = _Bus()

    await coordinator.execute_task_lifecycle(
        task,
        _Executor(stream, coordinator, task),  # type: ignore[arg-type]
        bus,  # type: ignore[arg-type]
        _inbound(locale, thread_id),
        hand_over_approval=hand_over if hand_over is not None else _HandOver(),
    )
    return coordinator, task, bus.published


async def _run(
    stream: StreamFactory,
    *,
    locale: str = "en",
    thread_id: str | None = None,
    timeout_seconds: float = 3600.0,
    hand_over: _HandOver | None = None,
) -> tuple[DelegationTask, OutboundMessage]:
    _coordinator, task, published = await _run_lifecycle(
        stream, locale=locale, thread_id=thread_id, timeout_seconds=timeout_seconds, hand_over=hand_over
    )
    assert len(published) == 1
    return task, published[0]


@pytest.mark.asyncio
async def test_the_delivery_is_the_final_reply_not_the_concatenated_snapshots() -> None:
    async def stream(_c: DelegationCoordinator, _t: DelegationTask) -> AsyncGenerator[object, None]:
        yield StreamingText(text="Hello")
        yield StreamingText(text="Hello world")
        yield _reply("Hello world")

    task, delivered = await _run(stream)

    assert task.status == DelegationStatus.COMPLETED
    assert delivered.content.startswith(f"✅ **Background task finished** `[{task.task_id}]` · took ")
    assert delivered.content.endswith("\n\nHello world")
    assert delivered.content.count("Hello world") == 1


@pytest.mark.asyncio
async def test_a_long_answer_is_delivered_whole_with_its_attachments_and_thread() -> None:
    long_answer = "\n".join(f"Finding {i}: the market grew." for i in range(400))
    deck = MediaAttachment(media_type=MediaType.DOCUMENT, path="/work/report.pptx", filename="report.pptx")

    async def stream(_c: DelegationCoordinator, _t: DelegationTask) -> AsyncGenerator[object, None]:
        yield _reply(long_answer, media=(deck,), thread_id="topic-9")

    _task, delivered = await _run(stream, thread_id="topic-9")

    assert len(long_answer) > 200
    assert delivered.content.endswith(long_answer)
    assert delivered.media == (deck,)
    assert delivered.thread_id == "topic-9"
    assert delivered.recipient_id == "chat-1"


@pytest.mark.asyncio
async def test_an_attachment_without_text_is_delivered_under_the_header_alone() -> None:
    deck = MediaAttachment(media_type=MediaType.DOCUMENT, path="/work/report.pptx", filename="report.pptx")

    async def stream(_c: DelegationCoordinator, _t: DelegationTask) -> AsyncGenerator[object, None]:
        yield _reply("", media=(deck,))

    task, delivered = await _run(stream)

    assert task.status == DelegationStatus.COMPLETED
    assert delivered.media == (deck,)
    assert delivered.content.startswith("✅ **Background task finished**")
    assert "\n" not in delivered.content
    assert "without a written result" not in delivered.content


@pytest.mark.asyncio
async def test_the_last_snapshot_is_delivered_in_the_requests_thread_when_there_is_no_final_reply() -> None:
    async def stream(_c: DelegationCoordinator, _t: DelegationTask) -> AsyncGenerator[object, None]:
        yield StreamingText(text="Hel")
        yield StreamingText(text="Hello world")

    task, delivered = await _run(stream, thread_id="topic-9")

    assert task.status == DelegationStatus.COMPLETED
    assert delivered.content.endswith("\n\nHello world")
    assert delivered.thread_id == "topic-9"
    assert delivered.recipient_id == "chat-1"
    assert delivered.user_id == "user-1"
    assert delivered.metadata == {"delegation_task_id": task.task_id, "locale": "en"}


@pytest.mark.asyncio
async def test_a_silent_run_says_so_instead_of_delivering_an_empty_message() -> None:
    async def stream(_c: DelegationCoordinator, _t: DelegationTask) -> AsyncGenerator[object, None]:
        if False:
            yield None

    task, delivered = await _run(stream)

    assert task.status == DelegationStatus.COMPLETED
    assert delivered.content.endswith("\n\nThe task finished without a written result.")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("locale", "header", "no_output"),
    [
        ("en", "✅ **Background task finished** `[{id}]` · took ", "The task finished without a written result."),
        ("zh-CN", "✅ **后台任务已完成** `[{id}]` · 用时 ", "任务已结束，但没有产出文字结果。"),
        (
            "ja",
            "✅ **バックグラウンドタスクが完了しました** `[{id}]` · 所要時間 ",
            "タスクは終了しましたが、文章の結果は出力されませんでした。",
        ),
    ],
)
async def test_the_delivery_speaks_the_senders_language(locale: str, header: str, no_output: str) -> None:
    async def stream(_c: DelegationCoordinator, _t: DelegationTask) -> AsyncGenerator[object, None]:
        if False:
            yield None

    task, delivered = await _run(stream, locale=locale)

    assert delivered.content.startswith(header.format(id=task.task_id))
    assert delivered.content.endswith(f"\n\n{no_output}")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("locale", "elapsed", "expected"),
    [
        ("en", 45, "took 45 s"),
        ("en", 125, "took 2 min 5 s"),
        ("zh-CN", 125, "用时 2 分 5 秒"),
        ("en", 0.4, "took 0 s"),
    ],
)
async def test_the_header_reports_how_long_the_task_ran(
    monkeypatch: pytest.MonkeyPatch, locale: str, elapsed: float, expected: str
) -> None:
    clock = iter([1_000.0, 1_000.0 + elapsed])  # the RUNNING transition, then the terminal one
    monkeypatch.setattr(coordinator_module, "time", SimpleNamespace(time=lambda: next(clock)))

    async def stream(_c: DelegationCoordinator, _t: DelegationTask) -> AsyncGenerator[object, None]:
        yield _reply("done")

    _task, delivered = await _run(stream, locale=locale)

    assert expected in delivered.content.split("\n")[0]


@pytest.mark.asyncio
async def test_a_failed_turn_reply_marks_the_task_failed_and_delivers_the_member_safe_text() -> None:
    async def stream(_c: DelegationCoordinator, _t: DelegationTask) -> AsyncGenerator[object, None]:
        yield _reply(_SAFE_FAILURE, error_type="billing", thread_id="topic-9")

    task, delivered = await _run(stream, thread_id="topic-9")

    assert task.status == DelegationStatus.FAILED
    assert task.error_message == _SAFE_FAILURE
    assert delivered.content.startswith(f"❌ **Background task failed** `[{task.task_id}]` · after ")
    assert delivered.content.endswith(f"\n\n{_SAFE_FAILURE}")
    assert "finished" not in delivered.content
    assert delivered.metadata == {"error_type": "billing"}
    assert delivered.thread_id == "topic-9"


@pytest.mark.asyncio
async def test_an_executor_exception_never_reaches_the_chat_and_is_logged_under_the_reference(
    caplog: pytest.LogCaptureFixture,
) -> None:
    async def stream(_c: DelegationCoordinator, _t: DelegationTask) -> AsyncGenerator[object, None]:
        if False:
            yield None
        raise RuntimeError(_RAW_ERROR)

    with caplog.at_level(logging.ERROR):
        task, delivered = await _run(stream, locale="zh-CN", thread_id="topic-9")

    assert task.status == DelegationStatus.FAILED
    assert delivered.content.startswith(f"❌ **后台任务失败** `[{task.task_id}]`")
    assert delivered.thread_id == "topic-9"
    for text in (task.error_message, delivered.content):
        assert "secret-token-42" not in text
        assert "Sandbox container" not in text
    ref = _REF.search(delivered.content)
    assert ref is not None
    assert ref.group(1) in task.error_message
    logged = [r.getMessage() for r in caplog.records if "secret-token-42" in r.getMessage()]
    assert len(logged) == 1
    assert f"[ref: {ref.group(1)}]" in logged[0]


@pytest.mark.asyncio
async def test_a_task_timed_out_while_running_stays_timed_out_and_its_partial_answer_is_not_delivered() -> None:
    """The stale-task reaper times a task out and cancels its stream; the stream's end must not turn it into a success."""

    async def stream(coordinator: DelegationCoordinator, task: DelegationTask) -> AsyncGenerator[object, None]:
        coordinator.update_task_status(task.task_id, DelegationStatus.TIMED_OUT)
        yield _reply("partial answer")

    task, delivered = await _run(stream, timeout_seconds=5400.0)

    assert task.status == DelegationStatus.TIMED_OUT
    assert delivered.content == f"⏱ **Background task stopped** `[{task.task_id}]` · it ran past the 90-minute limit."
    assert "partial answer" not in delivered.content


@pytest.mark.asyncio
async def test_the_timed_out_notice_is_localized() -> None:
    async def stream(coordinator: DelegationCoordinator, task: DelegationTask) -> AsyncGenerator[object, None]:
        coordinator.update_task_status(task.task_id, DelegationStatus.TIMED_OUT)
        if False:
            yield None

    task, delivered = await _run(stream, locale="zh-CN")

    assert delivered.content == f"⏱ **后台任务已中止** `[{task.task_id}]` · 运行超过 60 分钟的时限。"


_APPROVE = ProgressUpdate(
    label="shell needs approval: run the build",
    quick_replies=(QuickReply(label="Approve", text="/approve", required=True),),
)


@pytest.mark.asyncio
async def test_a_run_that_stops_at_a_tool_approval_is_handed_to_the_chat_not_announced_as_finished() -> None:
    """The executor ends the stream at the approval request; its leftover reply is not a result."""

    async def stream(_c: DelegationCoordinator, _t: DelegationTask) -> AsyncGenerator[object, None]:
        yield _APPROVE
        yield _reply("No response generated.")

    hand_over = _HandOver()
    _coordinator, task, published = await _run_lifecycle(stream, hand_over=hand_over)

    assert hand_over.requests == [_APPROVE]
    assert published == []
    assert task.status == DelegationStatus.COMPLETED


@pytest.mark.asyncio
async def test_an_approval_that_cannot_reach_the_chat_fails_the_task_and_says_so() -> None:
    async def stream(_c: DelegationCoordinator, _t: DelegationTask) -> AsyncGenerator[object, None]:
        yield _APPROVE

    task, delivered = await _run(stream, hand_over=_HandOver(RuntimeError(_RAW_ERROR)))

    assert task.status == DelegationStatus.FAILED
    assert delivered.content.startswith(f"❌ **Background task failed** `[{task.task_id}]`")
    assert "secret-token-42" not in delivered.content


@pytest.mark.asyncio
async def test_a_task_timed_out_at_an_approval_still_gets_its_stopped_notice() -> None:
    async def stream(coordinator: DelegationCoordinator, task: DelegationTask) -> AsyncGenerator[object, None]:
        yield _APPROVE
        coordinator.update_task_status(task.task_id, DelegationStatus.TIMED_OUT)

    hand_over = _HandOver()
    _coordinator, task, published = await _run_lifecycle(stream, hand_over=hand_over)

    assert hand_over.requests == []
    assert len(published) == 1
    assert published[0].content.startswith(f"⏱ **Background task stopped** `[{task.task_id}]`")


@pytest.mark.asyncio
async def test_progress_without_choices_does_not_hold_back_the_delivery() -> None:
    async def stream(_c: DelegationCoordinator, _t: DelegationTask) -> AsyncGenerator[object, None]:
        yield ProgressUpdate(label="Searching the web")
        yield _reply("Hello world")

    task, delivered = await _run(stream)

    assert task.status == DelegationStatus.COMPLETED
    assert delivered.content.endswith("\n\nHello world")


@pytest.mark.asyncio
async def test_a_handled_task_leaves_nothing_behind_in_the_coordinator() -> None:
    async def stream(_c: DelegationCoordinator, _t: DelegationTask) -> AsyncGenerator[object, None]:
        yield _reply("Hello world")

    coordinator, task, _published = await _run_lifecycle(stream)

    assert coordinator.get_task(task.task_id) is None
    assert coordinator.get_cancellation_token(task.task_id) is None
    assert coordinator.get_steering_token(task.task_id) is None
    assert coordinator.find_active_task("telegram", "chat-1", "user-1") is None
