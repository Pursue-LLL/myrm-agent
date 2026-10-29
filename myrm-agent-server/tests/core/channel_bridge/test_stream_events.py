"""Unit tests for channel harness stream event mapping."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from myrm_agent_harness.agent.errors import ToolStuckException
from myrm_agent_harness.toolkits.llms.errors.classifier import ErrorKind

from app.channels.types import ApprovalExpiry, FissionTopologyNode, FissionTopologyUpdate, ProgressUpdate, StreamingText
from app.core.channel_bridge.agent_executor.stream_events import iter_channel_stream_progress
from app.core.channel_bridge.executor_helpers import StreamAccumulator


async def _events(*items: dict[str, object]) -> AsyncIterator[dict[str, object]]:
    for item in items:
        yield item


@pytest.mark.asyncio
async def test_message_event_yields_writing_progress_and_streaming_text() -> None:
    acc = StreamAccumulator()
    progress = [
        item
        async for item in iter_channel_stream_progress(
            _events({"type": "message", "data": "Hello"}),
            acc,
            locale="en",
            session_key="",
        )
    ]
    assert len(progress) == 2
    assert isinstance(progress[0], ProgressUpdate)
    assert progress[0].label == "✍️ Writing response..."
    assert isinstance(progress[1], StreamingText)
    assert progress[1].text == "Hello"
    assert acc.draft.text == "Hello"


@pytest.mark.asyncio
async def test_tool_approval_request_carries_its_time_limit_and_the_session_of_the_run() -> None:
    acc = StreamAccumulator()
    event: dict[str, object] = {
        "type": "tool_approval_request",
        "data": {
            "actionRequests": [{"action": "bash", "description": "run ls"}],
            "extensions": {"timeout": {"seconds": 120, "behavior": "allow"}},
        },
    }
    session_key = "telegram:dm:u1:e=2026-10-26"
    progress = [item async for item in iter_channel_stream_progress(_events(event), acc, locale="en", session_key=session_key)]
    assert len(progress) == 1
    assert isinstance(progress[0], ProgressUpdate)
    assert progress[0].expiry == ApprovalExpiry(seconds=120, behavior="allow")
    assert progress[0].session_key == session_key


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("extensions", "expected"),
    [
        ({}, ApprovalExpiry(seconds=300, behavior="deny")),
        ({"timeout": {"seconds": "45", "behavior": "deny"}}, ApprovalExpiry(seconds=45, behavior="deny")),
        ({"timeout": {"seconds": 90, "behavior": "anything-else"}}, ApprovalExpiry(seconds=90, behavior="deny")),
    ],
)
async def test_tool_approval_request_defaults_to_denying_after_the_default_window(
    extensions: dict[str, object], expected: ApprovalExpiry
) -> None:
    event: dict[str, object] = {
        "type": "tool_approval_request",
        "data": {"actionRequests": [{"action": "bash", "description": "run ls"}], "extensions": extensions},
    }
    progress = [
        item async for item in iter_channel_stream_progress(_events(event), StreamAccumulator(), locale="en", session_key="")
    ]
    assert isinstance(progress[0], ProgressUpdate)
    assert progress[0].expiry == expected


@pytest.mark.asyncio
async def test_capability_gap_web_search_not_configured_yields_progress_update() -> None:
    acc = StreamAccumulator()
    event: dict[str, object] = {
        "type": "capability_gap",
        "data": {
            "tool_id": "web_search",
            "tool_group": "web",
            "reason": "not_configured",
            "display_message": "Web search is enabled but no search API is configured.",
        },
    }
    progress = [item async for item in iter_channel_stream_progress(_events(event), acc, locale="en", session_key="")]
    assert len(progress) == 1
    assert isinstance(progress[0], ProgressUpdate)
    assert progress[0].label == "Web search is enabled but no search API is configured."


@pytest.mark.asyncio
async def test_capability_gap_web_search_unreachable_yields_progress_update() -> None:
    acc = StreamAccumulator()
    event: dict[str, object] = {
        "type": "capability_gap",
        "data": {
            "tool_id": "web_search",
            "reason": "unreachable",
            "display_message": "Web search provider is unreachable.",
        },
    }
    progress = [item async for item in iter_channel_stream_progress(_events(event), acc, locale="en", session_key="")]
    assert len(progress) == 1
    assert isinstance(progress[0], ProgressUpdate)
    assert progress[0].label == "Web search provider is unreachable."


@pytest.mark.asyncio
async def test_capability_gap_web_search_skipped_when_display_message_empty() -> None:
    acc = StreamAccumulator()
    event: dict[str, object] = {
        "type": "capability_gap",
        "data": {
            "tool_id": "web_search",
            "reason": "not_configured",
            "display_message": "",
        },
    }
    progress = [item async for item in iter_channel_stream_progress(_events(event), acc, locale="en", session_key="")]
    assert len(progress) == 1
    assert isinstance(progress[0], ProgressUpdate)
    assert "search API" in progress[0].label


@pytest.mark.asyncio
async def test_fission_topology_update_is_passed_on_unchanged() -> None:
    acc = StreamAccumulator()
    update = FissionTopologyUpdate(
        fission_id="f1", nodes=(FissionTopologyNode(node_id="n1", agent_type="research", objective="A", status="running"),)
    )
    progress = [
        item
        async for item in iter_channel_stream_progress(
            _events({"type": "fission_topology", "data": update}),
            acc,
            locale="en",
            session_key="",
        )
    ]
    assert progress == [update]


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [{"nodes": ["a"]}, None])
async def test_a_fission_topology_event_without_an_update_is_dropped(payload: object) -> None:
    acc = StreamAccumulator()
    progress = [
        item
        async for item in iter_channel_stream_progress(
            _events({"type": "fission_topology", "data": payload}),
            acc,
            locale="en",
            session_key="",
        )
    ]
    assert progress == []


async def _consume(*events: dict[str, object]) -> StreamAccumulator:
    acc = StreamAccumulator()
    async for _ in iter_channel_stream_progress(_events(*events), acc, locale="en", session_key=""):
        pass
    return acc


_FAILOVER_RESTART: dict[str, object] = {"type": "status", "step_key": "model_failover", "restart": True}


@pytest.mark.asyncio
async def test_failover_restart_replaces_the_partial_answer_instead_of_splicing_it() -> None:
    acc = await _consume(
        {"type": "message", "data": "The capital of France is Pa"},
        _FAILOVER_RESTART,
        {"type": "message", "data": "Paris is the capital of France."},
    )

    assert acc.draft.text == "Paris is the capital of France."


@pytest.mark.asyncio
async def test_failover_restart_keeps_the_text_streamed_before_a_tool_step() -> None:
    acc = await _consume(
        {"type": "message", "data": "Let me check. "},
        {"type": "tool_start"},
        {"type": "message", "data": "The capital of France is Pa"},
        _FAILOVER_RESTART,
        {"type": "message", "data": "Paris is the capital of France."},
    )

    assert acc.draft.text == "Let me check. Paris is the capital of France."


@pytest.mark.asyncio
async def test_error_event_keeps_raw_text_and_error_kind() -> None:
    acc = await _consume(
        {
            "type": "error",
            "error": "Error code: 403 - raw provider body",
            "error_type": "PermissionDeniedError",
            "error_kind": "billing",
        }
    )

    assert acc.error_message == "PermissionDeniedError: Error code: 403 - raw provider body"
    assert acc.error_kind is ErrorKind.BILLING


@pytest.mark.asyncio
@pytest.mark.parametrize("error_kind", [None, "", "no_such_kind", 7])
async def test_error_event_without_a_known_kind_is_unknown(error_kind: object) -> None:
    event: dict[str, object] = {"type": "error", "error": "tool crashed"}
    if error_kind is not None:
        event["error_kind"] = error_kind

    acc = await _consume(event)

    assert acc.error_message == "tool crashed"
    assert acc.error_kind is ErrorKind.UNKNOWN


@pytest.mark.asyncio
async def test_later_error_event_replaces_the_earlier_one() -> None:
    acc = await _consume(
        {"type": "error", "error": "first", "error_kind": "billing"},
        {"type": "error", "error": "second", "error_kind": "timeout"},
        {"type": "error", "error": "third"},
    )

    assert acc.error_message == "third"
    assert acc.error_kind is ErrorKind.UNKNOWN


@pytest.mark.asyncio
async def test_loop_guard_pause_is_recorded_without_a_card() -> None:
    """The pause arrives as ``approval_required`` but waits on no answer: nothing to approve, so no card."""
    pause: dict[str, object] = {
        "type": "approval_required",
        "data": ToolStuckException("stuck").interrupt_payload("bash_code_execute_tool", "call-1"),
    }
    acc = StreamAccumulator()
    progress = [item async for item in iter_channel_stream_progress(_events(pause), acc, locale="en", session_key="")]

    assert progress == []
    assert acc.tool_stuck_paused is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "event",
    [
        {"type": "approval_required", "data": {"action_type": "bash"}},
        {"type": "approval_required"},
        {"type": "tool_approval_request", "data": {"actionRequests": [{"action": "bash", "description": "run ls"}]}},
        {"type": "message", "data": "hello"},
    ],
)
async def test_other_events_do_not_mark_the_turn_as_paused(event: dict[str, object]) -> None:
    acc = await _consume(event)

    assert acc.tool_stuck_paused is False
