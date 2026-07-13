"""Unit tests for channel harness stream event mapping."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from app.channels.types import ProgressUpdate, StreamingText
from app.core.channel_bridge.executor_helpers import StreamAccumulator
from app.core.channel_bridge.agent_executor.stream_events import (
    ChannelStreamEventState,
    iter_channel_stream_progress,
)


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
    progress = [
        item
        async for item in iter_channel_stream_progress(_events(event), acc, state)
    ]
    assert len(progress) == 1
    assert isinstance(progress[0], ProgressUpdate)
    assert state.approval_timeout_info == {"seconds": 120, "behavior": "allow"}


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
