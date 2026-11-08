"""Tests for TOOL_IMAGE_OUTPUT event emission and _handle_tool_result coverage.

Verifies that multimodal tool outputs (e.g., computer_use screenshots)
are detected and emitted as TOOL_IMAGE_OUTPUT events, and exercises
the normal, error, and hoisted-sources paths of _handle_tool_result.
"""

import json

import pytest
from langchain_core.messages import AIMessage, AIMessageChunk, ToolMessage

from myrm_agent_harness.agent.middlewares.tooling.tool_sources_hoisting import TOOL_SOURCES_KWARG
from myrm_agent_harness.agent.streaming.event_handlers import (
    _handle_tool_result,
    process_messages_chunk,
    process_updates_chunk,
)
from myrm_agent_harness.agent.streaming.source_tracker import SourceTracker
from myrm_agent_harness.agent.streaming.types import AgentEventType
from myrm_agent_harness.agent.types import AgentRunStatistics


@pytest.mark.asyncio
async def test_image_block_emits_tool_image_output():
    """ToolMessage with image content block should emit TOOL_IMAGE_OUTPUT."""
    msg = ToolMessage(
        content=[
            {"type": "text", "text": "Screenshot captured.\nResolution: 1920x1080"},
            {
                "type": "image",
                "id": "lc_test",
                "base64": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk",
                "mime_type": "image/jpeg",
            },
        ],
        name="desktop_snapshot_tool",
        tool_call_id="call_img_1",
    )

    events = []
    async for event in _handle_tool_result(msg, "msg_001", None):
        events.append(event)

    image_events = [e for e in events if e["type"] == AgentEventType.TOOL_IMAGE_OUTPUT.value]
    assert len(image_events) == 1

    img_event = image_events[0]
    assert img_event["tool_name"] == "desktop_snapshot_tool"
    assert img_event["data"]["base64"] == "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk"
    assert img_event["data"]["mime_type"] == "image/jpeg"
    assert img_event["messageId"] == "msg_001"


@pytest.mark.asyncio
async def test_no_image_block_no_event():
    """ToolMessage with only text content should not emit TOOL_IMAGE_OUTPUT."""
    msg = ToolMessage(
        content="Search completed. Found 3 results.",
        name="web_search",
        tool_call_id="call_txt_1",
    )

    events = []
    async for event in _handle_tool_result(msg, "msg_002", None):
        events.append(event)

    image_events = [e for e in events if e["type"] == AgentEventType.TOOL_IMAGE_OUTPUT.value]
    assert len(image_events) == 0


@pytest.mark.asyncio
async def test_list_content_without_image_no_event():
    """ToolMessage with list content but no image block should not emit TOOL_IMAGE_OUTPUT."""
    msg = ToolMessage(
        content=[
            {"type": "text", "text": "Some text output"},
        ],
        name="some_tool",
        tool_call_id="call_no_img",
    )

    events = []
    async for event in _handle_tool_result(msg, "msg_003", None):
        events.append(event)

    image_events = [e for e in events if e["type"] == AgentEventType.TOOL_IMAGE_OUTPUT.value]
    assert len(image_events) == 0


@pytest.mark.asyncio
async def test_image_block_default_mime_type():
    """Image block without explicit mime_type should default to image/jpeg."""
    msg = ToolMessage(
        content=[
            {
                "type": "image",
                "id": "lc_test_2",
                "base64": "AQIDBAUG",
            },
        ],
        name="desktop_vision_tool",
        tool_call_id="call_no_mime",
    )

    events = []
    async for event in _handle_tool_result(msg, "msg_004", None):
        events.append(event)

    image_events = [e for e in events if e["type"] == AgentEventType.TOOL_IMAGE_OUTPUT.value]
    assert len(image_events) == 1
    assert image_events[0]["data"]["mime_type"] == "image/jpeg"


@pytest.mark.asyncio
async def test_multiple_image_blocks_all_emitted():
    """All image blocks in a tool result should be emitted."""
    msg = ToolMessage(
        content=[
            {"type": "text", "text": "Two screenshots"},
            {"type": "image", "id": "lc_1", "base64": "FIRST_IMAGE", "mime_type": "image/jpeg"},
            {"type": "image", "id": "lc_2", "base64": "SECOND_IMAGE", "mime_type": "image/png"},
        ],
        name="desktop_snapshot_tool",
        tool_call_id="call_multi",
    )

    events = []
    async for event in _handle_tool_result(msg, "msg_005", None):
        events.append(event)

    image_events = [e for e in events if e["type"] == AgentEventType.TOOL_IMAGE_OUTPUT.value]
    assert len(image_events) == 2
    assert image_events[0]["data"]["base64"] == "FIRST_IMAGE"
    assert image_events[1]["data"]["base64"] == "SECOND_IMAGE"


@pytest.mark.asyncio
async def test_error_tool_message_no_image_event():
    """Error ToolMessage should not emit TOOL_IMAGE_OUTPUT."""
    msg = ToolMessage(
        content="ToolExecutionError: Screenshot failed.",
        name="desktop_snapshot_tool",
        tool_call_id="call_err",
        status="error",
    )

    events = []
    async for event in _handle_tool_result(msg, "msg_006", None):
        events.append(event)

    image_events = [e for e in events if e["type"] == AgentEventType.TOOL_IMAGE_OUTPUT.value]
    assert len(image_events) == 0


@pytest.mark.asyncio
async def test_image_block_without_base64_no_event():
    """Image block without base64 data should not emit TOOL_IMAGE_OUTPUT."""
    msg = ToolMessage(
        content=[
            {"type": "image", "id": "lc_empty", "mime_type": "image/jpeg"},
        ],
        name="desktop_snapshot_tool",
        tool_call_id="call_no_b64",
    )

    events = []
    async for event in _handle_tool_result(msg, "msg_007", None):
        events.append(event)

    image_events = [e for e in events if e["type"] == AgentEventType.TOOL_IMAGE_OUTPUT.value]
    assert len(image_events) == 0


# ==================== sources carried in additional_kwargs ====================


async def _events_of(msg: ToolMessage, tracker: SourceTracker | None) -> list[dict[str, object]]:
    return [event async for event in _handle_tool_result(msg, "msg_src", tracker)]


@pytest.mark.asyncio
async def test_hoisted_sources_emit_the_reviewing_step_and_the_sources_event() -> None:
    """Sources in ``additional_kwargs`` reach the tracker, which numbers them and returns the new ones."""
    msg = ToolMessage(
        content="Found two pages.",
        name="web_search_tool",
        tool_call_id="call_s1",
        additional_kwargs={
            TOOL_SOURCES_KWARG: [
                {"url": "https://a.test", "title": "A"},
                {"url": "https://b.test", "title": "B"},
            ]
        },
    )

    events = await _events_of(msg, SourceTracker())

    expected = [
        {"url": "https://a.test", "title": "A", "index": 1},
        {"url": "https://b.test", "title": "B", "index": 2},
    ]
    assert [e["type"] for e in events] == [AgentEventType.TASKS_STEPS.value, AgentEventType.SOURCES.value]
    assert events[0]["step_key"] == "reviewing_sources"
    assert events[0]["count"] == 2
    assert events[0]["data"] == expected
    assert events[1]["data"] == expected


@pytest.mark.asyncio
async def test_an_envelope_left_in_the_content_is_not_read_for_sources() -> None:
    """Only the hoisted kwarg carries sources; a ``metadata.sources`` still inside the text is not consulted."""
    msg = ToolMessage(
        content=json.dumps({"content": "found", "metadata": {"sources": [{"url": "https://x.com"}]}}),
        name="web_search_tool",
        tool_call_id="call_s2",
    )

    assert await _events_of(msg, SourceTracker()) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("sources", [[], None, "https://x.com", {"url": "https://x.com"}])
async def test_a_sources_kwarg_that_is_not_a_non_empty_list_emits_nothing(sources: object) -> None:
    msg = ToolMessage(
        content="found",
        name="web_search_tool",
        tool_call_id="call_s3",
        additional_kwargs={TOOL_SOURCES_KWARG: sources},
    )

    assert await _events_of(msg, SourceTracker()) == []


@pytest.mark.asyncio
async def test_hoisted_sources_without_a_tracker_emit_nothing() -> None:
    msg = ToolMessage(
        content="found",
        name="web_search_tool",
        tool_call_id="call_s4",
        additional_kwargs={TOOL_SOURCES_KWARG: [{"url": "https://x.com"}]},
    )

    assert await _events_of(msg, None) == []


@pytest.mark.asyncio
async def test_a_source_the_tracker_already_knows_is_not_emitted_again() -> None:
    tracker = SourceTracker()
    msg = ToolMessage(
        content="found",
        name="web_search_tool",
        tool_call_id="call_s5",
        additional_kwargs={TOOL_SOURCES_KWARG: [{"url": "https://x.com"}]},
    )

    assert len(await _events_of(msg, tracker)) == 2
    assert await _events_of(msg, tracker) == []


@pytest.mark.asyncio
async def test_a_failed_result_emits_its_error_step_and_no_sources() -> None:
    msg = ToolMessage(
        content="boom",
        name="web_search_tool",
        tool_call_id="call_s6",
        status="error",
        additional_kwargs={TOOL_SOURCES_KWARG: [{"url": "https://x.com"}]},
    )

    events = await _events_of(msg, SourceTracker())

    assert [e["type"] for e in events] == [AgentEventType.TASKS_STEPS.value]
    assert events[0]["status"] == "error"


# ==================== _handle_tool_result normal path tests ====================


@pytest.mark.asyncio
async def test_normal_string_result_no_events():
    """Normal string result with no source_tracker should yield zero events."""
    msg = ToolMessage(
        content="Task completed successfully.",
        name="bash_code_execute_tool",
        tool_call_id="call_norm",
    )

    events = []
    async for event in _handle_tool_result(msg, "msg_norm", None):
        events.append(event)

    assert len(events) == 0


@pytest.mark.asyncio
async def test_error_with_category_and_hint():
    """Error ToolMessage with error_category and error_hint should propagate them."""
    msg = ToolMessage(
        content="ToolExecutionError: Permission denied",
        name="file_write",
        tool_call_id="call_err_cat",
        status="error",
        additional_kwargs={
            "error_category": "permission_error",
            "error_hint": "Check file permissions",
        },
    )

    events = []
    async for event in _handle_tool_result(msg, "msg_err_cat", None):
        events.append(event)

    assert len(events) == 1
    assert events[0]["type"] == AgentEventType.TASKS_STEPS.value
    assert events[0]["status"] == "error"
    assert events[0]["error_category"] == "permission_error"
    assert events[0]["error_hint"] == "Check file permissions"


# ==================== process_updates_chunk tests ====================


@pytest.mark.asyncio
async def test_process_updates_empty_node():
    """Empty node output should be skipped."""
    stats = AgentRunStatistics()
    data = {"agent": {}}

    events = []
    async for event in process_updates_chunk(data, stats, "msg_u1"):
        events.append(event)

    assert len(events) == 0


@pytest.mark.asyncio
async def test_process_updates_no_messages_key():
    """Node output without 'messages' key should be skipped."""
    stats = AgentRunStatistics()
    data = {"agent": {"some_key": "some_value"}}

    events = []
    async for event in process_updates_chunk(data, stats, "msg_u2"):
        events.append(event)

    assert len(events) == 0
    assert stats.node_execution_count == 1


@pytest.mark.asyncio
async def test_process_updates_tool_call():
    """AIMessage with tool_calls should emit TASKS_STEPS."""
    stats = AgentRunStatistics()
    ai_msg = AIMessage(
        content="",
        tool_calls=[{"name": "web_search", "args": {"query": "test"}, "id": "tc_1"}],
    )
    data = {"agent": {"messages": [ai_msg]}}

    events = []
    async for event in process_updates_chunk(data, stats, "msg_u3"):
        events.append(event)

    assert any(e["type"] == AgentEventType.TASKS_STEPS.value for e in events)
    assert stats.tool_call_count == 1


@pytest.mark.asyncio
async def test_process_updates_tool_result():
    """ToolMessage should be processed through _handle_tool_result."""
    stats = AgentRunStatistics()
    tool_msg = ToolMessage(content="Result text", name="bash_code_execute_tool", tool_call_id="tc_2")
    data = {"agent": {"messages": [tool_msg]}}

    events = []
    async for event in process_updates_chunk(data, stats, "msg_u4"):
        events.append(event)

    # No source_tracker, so normal ToolMessage with plain string yields no events
    assert len(events) == 0


@pytest.mark.asyncio
async def test_process_updates_empty_ai_message_skipped():
    """Empty AIMessage (no content, no tool_calls) should be skipped from collected_messages."""
    stats = AgentRunStatistics()
    empty_ai = AIMessage(content="")
    collected: list = []
    data = {"agent": {"messages": [empty_ai]}}

    events = []
    async for event in process_updates_chunk(data, stats, "msg_u5", collected):
        events.append(event)

    assert len(collected) == 0


@pytest.mark.asyncio
async def test_process_updates_ai_with_content_collected():
    """AIMessage with content should be added to collected_messages."""
    stats = AgentRunStatistics()
    ai_msg = AIMessage(content="Hello world")
    collected: list = []
    data = {"agent": {"messages": [ai_msg]}}

    events = []
    async for event in process_updates_chunk(data, stats, "msg_u6", collected):
        events.append(event)

    assert len(collected) == 1


# ==================== process_messages_chunk tests ====================


def test_messages_chunk_invalid_data():
    """Invalid data (not a tuple) should yield nothing."""
    stats = AgentRunStatistics()
    events = list(process_messages_chunk("not_a_tuple", stats, "msg_m1"))
    assert len(events) == 0


def test_messages_chunk_none_metadata():
    """None metadata should yield nothing."""
    stats = AgentRunStatistics()
    chunk = AIMessageChunk(content="hello")
    events = list(process_messages_chunk((chunk, None), stats, "msg_m2"))
    assert len(events) == 0


def test_messages_chunk_non_model_node():
    """Non-model node should yield nothing."""
    stats = AgentRunStatistics()
    chunk = AIMessageChunk(content="hello")
    events = list(process_messages_chunk((chunk, {"langgraph_node": "tools"}), stats, "msg_m3"))
    assert len(events) == 0


def test_messages_chunk_model_with_content():
    """Model node with text content should yield MESSAGE event."""
    stats = AgentRunStatistics()
    chunk = AIMessageChunk(content="Answer text")
    events = list(process_messages_chunk((chunk, {"langgraph_node": "model"}), stats, "msg_m4"))

    assert len(events) >= 1
    msg_events = [e for e, _ in events if e["type"] == AgentEventType.MESSAGE.value]
    assert len(msg_events) == 1
    assert stats.message_chunk_count == 1


def test_messages_chunk_tool_call_suppresses_text():
    """Tool call chunk should emit TOOL_START and suppress text."""
    stats = AgentRunStatistics()
    chunk = AIMessageChunk(
        content="",
        tool_calls=[{"name": "web_search", "args": {}, "id": "tc_chunk"}],
    )
    events = list(process_messages_chunk((chunk, {"langgraph_node": "model"}), stats, "msg_m5"))

    tool_start_events = [e for e, is_ts in events if is_ts]
    assert len(tool_start_events) >= 1


def test_messages_chunk_reasoning_content():
    """Reasoning content (DeepSeek format) should yield REASONING event."""
    stats = AgentRunStatistics()
    chunk = AIMessageChunk(
        content="",
        additional_kwargs={"reasoning_content": "Let me think..."},
    )
    events = list(process_messages_chunk((chunk, {"langgraph_node": "model"}), stats, "msg_m6"))

    reasoning_events = [e for e, _ in events if e["type"] == AgentEventType.REASONING.value]
    assert len(reasoning_events) == 1
    assert reasoning_events[0]["data"] == "Let me think..."


def test_messages_chunk_anthropic_thinking():
    """Anthropic thinking block should yield REASONING event."""
    stats = AgentRunStatistics()
    chunk = AIMessageChunk(
        content=[{"type": "thinking", "thinking": "Considering options..."}],
    )
    events = list(process_messages_chunk((chunk, {"langgraph_node": "model"}), stats, "msg_m7"))

    reasoning_events = [e for e, _ in events if e["type"] == AgentEventType.REASONING.value]
    assert len(reasoning_events) == 1


def test_messages_chunk_reasoning_is_sanitized_and_scrubbed() -> None:
    """Reasoning content should pass through the same scrub pipeline as message text."""
    stats = AgentRunStatistics()
    raw_reasoning = "api_key=sk-test-12345 path=/Users/alice/private_project"
    chunk = AIMessageChunk(
        content="",
        additional_kwargs={"reasoning_content": raw_reasoning},
    )
    events = list(process_messages_chunk((chunk, {"langgraph_node": "model"}), stats, "msg_m8"))

    reasoning_events = [e for e, _ in events if e["type"] == AgentEventType.REASONING.value]
    assert len(reasoning_events) == 1
    scrubbed = str(reasoning_events[0]["data"])
    assert "sk-test-12345" not in scrubbed
    assert "/Users/alice" not in scrubbed
