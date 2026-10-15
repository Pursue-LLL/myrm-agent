"""Unit tests for channel harness stream event mapping."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from app.channels.types import ProgressUpdate, StreamingText
from app.core.channel_bridge.agent_executor.stream_events import (
    ChannelStreamEventState,
    iter_channel_stream_progress,
)
from app.core.channel_bridge.executor_helpers import StreamAccumulator


async def _events(*items: dict[str, object]) -> AsyncIterator[dict[str, object]]:
    for item in items:
        yield item


@pytest.mark.asyncio
async def test_message_event_yields_writing_progress_and_streaming_text() -> None:
    acc = StreamAccumulator()
    state = ChannelStreamEventState()
    progress = [
        item
        async for item in iter_channel_stream_progress(
            _events({"type": "message", "data": "Hello"}),
            acc,
            state,
        )
    ]
    assert len(progress) == 2
    assert isinstance(progress[0], ProgressUpdate)
    assert progress[0].label == "✍️ Writing response..."
    assert isinstance(progress[1], StreamingText)
    assert progress[1].text == "Hello"
    assert acc.chunks == ["Hello"]


@pytest.mark.asyncio
async def test_tool_approval_request_sets_timeout_state() -> None:
    acc = StreamAccumulator()
    state = ChannelStreamEventState()
    event = {
        "type": "tool_approval_request",
        "data": {
            "actionRequests": [{"action": "bash", "description": "run ls"}],
            "extensions": {"timeout": {"seconds": 120, "behavior": "allow"}},
        },
    }
    progress = [item async for item in iter_channel_stream_progress(_events(event), acc, state)]
    assert len(progress) == 1
    assert isinstance(progress[0], ProgressUpdate)
    assert state.approval_timeout_info == {"seconds": 120, "behavior": "allow"}


@pytest.mark.asyncio
async def test_capability_gap_web_search_not_configured_yields_progress_update() -> None:
    acc = StreamAccumulator()
    state = ChannelStreamEventState()
    event = {
        "type": "capability_gap",
        "data": {
            "tool_id": "web_search",
            "tool_group": "web",
            "reason": "not_configured",
            "display_message": "Web search is enabled but no search API is configured.",
        },
    }
    progress = [item async for item in iter_channel_stream_progress(_events(event), acc, state)]
    assert len(progress) == 1
    assert isinstance(progress[0], ProgressUpdate)
    assert progress[0].label == "Web search is enabled but no search API is configured."


@pytest.mark.asyncio
async def test_capability_gap_web_search_unreachable_yields_progress_update() -> None:
    acc = StreamAccumulator()
    state = ChannelStreamEventState()
    event = {
        "type": "capability_gap",
        "data": {
            "tool_id": "web_search",
            "reason": "unreachable",
            "display_message": "Web search provider is unreachable.",
        },
    }
    progress = [item async for item in iter_channel_stream_progress(_events(event), acc, state)]
    assert len(progress) == 1
    assert isinstance(progress[0], ProgressUpdate)
    assert progress[0].label == "Web search provider is unreachable."


@pytest.mark.asyncio
async def test_capability_gap_web_search_skipped_when_display_message_empty() -> None:
    acc = StreamAccumulator()
    state = ChannelStreamEventState()
    event = {
        "type": "capability_gap",
        "data": {
            "tool_id": "web_search",
            "reason": "not_configured",
            "display_message": "",
        },
    }
    progress = [item async for item in iter_channel_stream_progress(_events(event), acc, state)]
    assert len(progress) == 1
    assert isinstance(progress[0], ProgressUpdate)
    assert "search API" in progress[0].label


@pytest.mark.asyncio
async def test_fission_topology_yields_raw_data() -> None:
    acc = StreamAccumulator()
    state = ChannelStreamEventState()
    payload = {"nodes": ["a"]}
    progress = [
        item
        async for item in iter_channel_stream_progress(
            _events({"type": "fission_topology", "data": payload}),
            acc,
            state,
        )
    ]
    assert progress == [payload]


async def _consume(*events: dict[str, object]) -> StreamAccumulator:
    acc = StreamAccumulator()
    async for _ in iter_channel_stream_progress(_events(*events), acc, ChannelStreamEventState()):
        pass
    return acc


@pytest.mark.asyncio
async def test_error_event_keeps_raw_text_and_harness_diagnostic() -> None:
    acc = await _consume(
        {
            "type": "error",
            "error": "Error code: 403 - raw provider body",
            "error_type": "PermissionDeniedError",
            "diagnostic_result": {
                "error_type": "billing",
                "user_message": "Your API account balance is insufficient",
                "resolution_steps": ["Top up your account", 7, "Switch to another model"],
                "locale": "en",
            },
        }
    )

    assert acc.error_message == "PermissionDeniedError: Error code: 403 - raw provider body"
    assert acc.error_user_message == "Your API account balance is insufficient"
    assert acc.error_steps == ["Top up your account", "Switch to another model"]


@pytest.mark.asyncio
async def test_error_event_without_diagnostic_leaves_only_raw_text() -> None:
    acc = await _consume({"type": "error", "error": "tool crashed"})

    assert acc.error_message == "tool crashed"
    assert acc.error_user_message is None
    assert acc.error_steps == []


@pytest.mark.asyncio
async def test_later_error_event_replaces_the_earlier_diagnostic() -> None:
    acc = await _consume(
        {"type": "error", "error": "first", "diagnostic_result": {"user_message": "Diagnosed", "resolution_steps": ["a"]}},
        {"type": "error", "error": "second"},
    )

    assert acc.error_message == "second"
    assert acc.error_user_message is None
    assert acc.error_steps == []


@pytest.mark.asyncio
async def test_error_event_with_blank_diagnostic_message_falls_back_to_raw_text() -> None:
    acc = await _consume({"type": "error", "error": "boom", "diagnostic_result": {"user_message": "", "resolution_steps": ["x"]}})

    assert acc.error_user_message is None
