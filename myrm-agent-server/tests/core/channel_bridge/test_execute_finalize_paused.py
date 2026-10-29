"""A turn the loop guard paused replies that the step was stopped, never that nothing came back.

The pause reaches the channel stream as an ``approval_required`` event (see ``test_stream_events``) but waits on no
answer, so the reply must not look like an approval card, a crash or an empty turn. These tests run the real event
mapper into the real finalize, the way ``ChannelAgentExecutor`` does.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from types import SimpleNamespace

import pytest
from myrm_agent_harness.agent.errors import ToolStuckException
from myrm_agent_harness.agent.streaming.interrupt_events import interrupt_events
from myrm_agent_harness.toolkits.llms.errors.classifier import ErrorKind

from app.channels.routing.friendly_errors import ERROR_TYPE_METADATA_KEY, is_error_reply
from app.channels.types import InboundMessage, OutboundMessage
from app.core.channel_bridge.agent_executor.stream_events import iter_channel_stream_progress
from app.core.channel_bridge.executor_helpers import StreamAccumulator
from tests.core.channel_bridge.test_execute_finalize import _finalize


def _harness_pause_event() -> dict[str, object]:
    """The event the harness streams for a loop guard pause, built by its own interrupt translator."""
    payload = ToolStuckException("stuck").interrupt_payload("file_read_tool", "call-secret-1")
    return interrupt_events([SimpleNamespace(value=payload, id="interrupt-1")], "msg-1", {})[0]


_PAUSE = _harness_pause_event()
_EN_NOTICE = "That step kept failing, so I stopped here. Tell me how you'd like to go on."


def _message(locale: str) -> InboundMessage:
    return InboundMessage(
        channel="telegram",
        sender_id="user-1",
        content="hi",
        sent_timezone="UTC",
        metadata={"platform_locale": locale},
    )


async def _events(*items: dict[str, object]) -> AsyncIterator[dict[str, object]]:
    for item in items:
        yield item


async def _run_turn(*events: dict[str, object], locale: str = "en") -> tuple[str, OutboundMessage]:
    """Map ``events`` into an accumulator, finalize it, and return (persisted text, reply)."""
    acc = StreamAccumulator()
    async for _ in iter_channel_stream_progress(_events(*events), acc, locale=locale, session_key=""):
        pass
    persist_mock, reply = await _finalize(acc, ((), frozenset()), message=_message(locale))
    return str(persist_mock.call_args.args[1]), reply


@pytest.mark.asyncio
async def test_a_paused_turn_without_text_says_the_step_was_stopped() -> None:
    persisted, reply = await _run_turn(_PAUSE)

    assert reply.content == _EN_NOTICE
    assert persisted == _EN_NOTICE
    assert "No response generated" not in reply.content


@pytest.mark.asyncio
async def test_the_notice_leaks_no_technical_detail() -> None:
    _persisted, reply = await _run_turn(_PAUSE)

    for leaked in ("file_read_tool", "call-secret-1", "tool_stuck", "ToolStuck", "approval"):
        assert leaked not in reply.content


@pytest.mark.asyncio
async def test_text_streamed_before_the_pause_is_kept_and_the_notice_follows() -> None:
    persisted, reply = await _run_turn({"type": "message", "data": "Let me read that file."}, _PAUSE)

    assert reply.content == f"Let me read that file.\n\n{_EN_NOTICE}"
    assert persisted == reply.content


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("locale", "notice"),
    [
        ("zh-CN", "这一步连续失败，我先停在这里了。告诉我接下来怎么处理吧。"),
        ("ja", "この手順が続けて失敗したため、ここで止めました。どう進めるか教えてください。"),
    ],
)
async def test_the_notice_follows_the_sender_locale(locale: str, notice: str) -> None:
    _persisted, reply = await _run_turn(_PAUSE, locale=locale)

    assert reply.content == notice


@pytest.mark.asyncio
async def test_a_paused_turn_stays_flagged_so_a_delegated_task_is_not_reported_as_done() -> None:
    _persisted, reply = await _run_turn(_PAUSE)

    assert is_error_reply(reply)
    assert reply.metadata is not None
    assert reply.metadata[ERROR_TYPE_METADATA_KEY] == "tool_stuck"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "events",
    [
        pytest.param((_PAUSE,), id="without_text"),
        pytest.param(({"type": "message", "data": "Let me read that file."}, _PAUSE), id="after_text"),
    ],
)
async def test_a_paused_turn_leaves_a_log_line_naming_the_sender(
    events: tuple[dict[str, object], ...], caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.WARNING):
        await _run_turn(*events)

    logged = [r.getMessage() for r in caplog.records if "user-1" in r.getMessage()]
    assert len(logged) == 1
    assert "loop guard" in logged[0]
    assert "empty LLM response" not in logged[0]


@pytest.mark.asyncio
async def test_a_paused_turn_with_a_fatal_error_reports_the_error() -> None:
    error: dict[str, object] = {"type": "error", "error": "provider down", "error_kind": "timeout"}
    _persisted, reply = await _run_turn(_PAUSE, error)

    assert "timed out" in reply.content
    assert _EN_NOTICE not in reply.content
    assert reply.metadata is not None
    assert reply.metadata[ERROR_TYPE_METADATA_KEY] == ErrorKind.TIMEOUT.value


@pytest.mark.asyncio
async def test_a_turn_that_really_came_back_empty_keeps_its_own_notice() -> None:
    _persisted, reply = await _run_turn({"type": "message_end"})

    assert reply.content == "No response generated."
    assert reply.metadata is not None
    assert reply.metadata[ERROR_TYPE_METADATA_KEY] == "empty_response"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "approval",
    [
        {"type": "approval_required", "data": {"action_type": "bash"}},
        {"type": "approval_required", "data": {}},
        {"type": "tool_approval_request", "data": {"actionRequests": [{"action": "bash", "description": "run ls"}]}},
    ],
)
async def test_a_real_approval_request_is_not_taken_for_a_pause(approval: dict[str, object]) -> None:
    _persisted, reply = await _run_turn(approval)

    assert reply.content == "No response generated."
    assert reply.metadata is not None
    assert reply.metadata[ERROR_TYPE_METADATA_KEY] == "empty_response"
