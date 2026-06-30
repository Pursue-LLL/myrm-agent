"""Integration test: tool_image_output event → SSEEnvelope serialization.

Validates the full harness → server → SSE pipeline for MCP image events:
1. process_updates_chunk (harness) emits tool_image_output events
2. SSEEnvelope.from_any serializes them into valid SSE chunks
3. JSON-parsed SSE chunks contain correct image data

No external LLM or MCP service required — tests the internal pipeline only.
"""

import json

import pytest
from langchain_core.messages import ToolMessage

from app.schemas.streaming import SSEEnvelope
from myrm_agent_harness.agent.streaming.event_handlers import process_updates_chunk
from myrm_agent_harness.agent.types import AgentRunStatistics


def _parse_sse_chunk(chunk: str) -> dict[str, object]:
    """Parse an SSE chunk string into a dict."""
    for line in chunk.strip().splitlines():
        if line.startswith("data: "):
            return json.loads(line[6:])
    raise ValueError(f"No 'data:' line in SSE chunk: {chunk!r}")


@pytest.mark.asyncio
async def test_base64_image_event_round_trips_through_sse():
    """base64 image → process_updates_chunk → SSEEnvelope → SSE string → JSON parse."""
    msg = ToolMessage(
        content=[{"type": "image", "base64": "iVBORw0KGgo=", "mime_type": "image/png"}],
        tool_call_id="tc_001",
        name="screenshot_tool",
    )
    data = {"agent": {"messages": [msg]}}
    stats = AgentRunStatistics()

    events = [e async for e in process_updates_chunk(data, stats, "msg_001")]
    image_events = [e for e in events if e["type"] == "tool_image_output"]
    assert len(image_events) == 1

    envelope = SSEEnvelope.from_any(image_events[0])
    sse_chunk = envelope.to_sse_chunk()

    parsed = _parse_sse_chunk(sse_chunk)
    assert parsed["type"] == "tool_image_output"
    assert parsed["data"]["base64"] == "iVBORw0KGgo="
    assert parsed["data"]["mime_type"] == "image/png"
    assert parsed["tool_name"] == "screenshot_tool"


@pytest.mark.asyncio
async def test_url_image_event_round_trips_through_sse():
    """URL image → process_updates_chunk → SSEEnvelope → SSE string → JSON parse."""
    msg = ToolMessage(
        content=[{"type": "image", "url": "https://example.com/img.png", "mime_type": "image/png"}],
        tool_call_id="tc_002",
        name="mcp_chart_tool",
    )
    data = {"agent": {"messages": [msg]}}
    stats = AgentRunStatistics()

    events = [e async for e in process_updates_chunk(data, stats, "msg_002")]
    image_events = [e for e in events if e["type"] == "tool_image_output"]
    assert len(image_events) == 1

    envelope = SSEEnvelope.from_any(image_events[0])
    sse_chunk = envelope.to_sse_chunk()

    parsed = _parse_sse_chunk(sse_chunk)
    assert parsed["type"] == "tool_image_output"
    assert parsed["data"]["url"] == "https://example.com/img.png"
    assert parsed["data"]["mime_type"] == "image/png"
    assert "base64" not in parsed["data"]
    assert parsed["tool_name"] == "mcp_chart_tool"


@pytest.mark.asyncio
async def test_mixed_images_produce_multiple_sse_events():
    """Mixed base64 + URL images → each gets its own SSE event."""
    msg = ToolMessage(
        content=[
            {"type": "image", "base64": "b64data", "mime_type": "image/jpeg"},
            {"type": "text", "text": "Here are your charts"},
            {"type": "image", "url": "https://cdn.example.com/chart.png", "mime_type": "image/png"},
        ],
        tool_call_id="tc_003",
        name="multi_output_tool",
    )
    data = {"agent": {"messages": [msg]}}
    stats = AgentRunStatistics()

    events = [e async for e in process_updates_chunk(data, stats, "msg_003")]
    image_events = [e for e in events if e["type"] == "tool_image_output"]
    assert len(image_events) == 2

    chunks = [_parse_sse_chunk(SSEEnvelope.from_any(e).to_sse_chunk()) for e in image_events]
    assert chunks[0]["data"]["base64"] == "b64data"
    assert chunks[1]["data"]["url"] == "https://cdn.example.com/chart.png"


@pytest.mark.asyncio
async def test_empty_image_block_is_not_serialized():
    """Image block without base64 or url should not produce any SSE event."""
    msg = ToolMessage(
        content=[{"type": "image"}],
        tool_call_id="tc_004",
        name="broken_tool",
    )
    data = {"agent": {"messages": [msg]}}
    stats = AgentRunStatistics()

    events = [e async for e in process_updates_chunk(data, stats, "msg_004")]
    image_events = [e for e in events if e["type"] == "tool_image_output"]
    assert len(image_events) == 0
