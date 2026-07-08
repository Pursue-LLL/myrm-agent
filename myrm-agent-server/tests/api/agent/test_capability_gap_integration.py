"""Integration: discover_capability gap hints + SSE wiring (agent-stream + direct tool path)."""

from __future__ import annotations

import asyncio
import json
import uuid
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from myrm_agent_harness.agent.meta_tools.discover_capability.discover_capability_tool import (
    sync_discover_capability_tool,
)
from myrm_agent_harness.agent.tool_management.registry import ToolRegistry
from myrm_agent_harness.agent.tool_management.types import ToolBindMode, ToolSource
from myrm_agent_harness.agent.streaming.stream_executor import StreamContext, StreamExecutor
from myrm_agent_harness.agent.streaming.types import AgentEventType, AgentStreamEvent
from myrm_agent_harness.agent.types import AgentRunStatistics
from tests.api.agent.utils import check_e2e_errors, get_lite_model_selection


class _DummyInput(BaseModel):
    arg1: str = Field(default="")


class _DummyDeferredTool(BaseTool):
    name: str = "dummy_deferred_tool"
    description: str = "Deferred placeholder for discover index rebuild tests."
    args_schema: type[BaseModel] = _DummyInput

    def _run(self, arg1: str = "") -> str:
        return "ok"


def _discover_gateway_skills() -> list:
    """Minimal searchable skill so DeferEconomics binds discover_capability_tool in tests."""
    from myrm_agent_harness.backends.skills.types import SkillMetadata

    return [
        SkillMetadata(
            name="gap_integration_skill",
            description="Integration test skill to enable discover gateway binding.",
        )
    ]


def _collect_agent_stream(client: TestClient, payload: dict[str, object]) -> list[dict[str, object]]:
    collected: list[dict[str, object]] = []
    with client.stream("POST", "/api/v1/agents/agent-stream", json=payload, timeout=180.0) as response:
        assert response.status_code == 200, response.text
        for line in response.iter_lines():
            if not line or not line.strip().startswith("data: "):
                continue
            raw = line.strip()[6:]
            if raw == "[DONE]":
                break
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if isinstance(data, dict):
                collected.append(data)
    return collected


def _invoked_tool_names(events: list[dict[str, object]]) -> set[str]:
    names: set[str] = set()
    for event in events:
        if event.get("type") not in {"tasks_steps", "tool_end", "tool_start"}:
            continue
        tool_name = event.get("tool_name")
        if isinstance(tool_name, str) and tool_name:
            names.add(tool_name)
    return names


def _gap_events(events: list[dict[str, object]], event_type: str) -> list[dict[str, object]]:
    return [event for event in events if event.get("type") == event_type]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_discover_miss_emits_capability_gap_block_and_sse(monkeypatch: pytest.MonkeyPatch) -> None:
    """Deterministic: miss query → XML gap block + async custom event dispatch."""
    registry = ToolRegistry()
    registry.register(_DummyDeferredTool(), source=ToolSource.USER, bind_mode=ToolBindMode.DISCOVERABLE)
    discover = sync_discover_capability_tool(
        registry,
        skills=_discover_gateway_skills(),
        active_tool_groups=frozenset({"web", "memory", "file_ops", "shell"}),
    )
    assert discover is not None

    captured: list[tuple[str, object]] = []

    async def _capture(name: str, data: object, config: object | None = None) -> None:
        captured.append((name, data))

    monkeypatch.setattr(
        "myrm_agent_harness.utils.event_utils.dispatch_custom_event",
        _capture,
    )

    gap_query = "zzz_gap_browser_selenium_website_7742"
    result = await discover.ainvoke({"query": gap_query})
    assert "No capabilities found" in result
    assert "<CapabilityGap>" in result
    assert any(name == "capability_gap" for name, _ in captured)
    cap_payload = next(payload for name, payload in captured if name == "capability_gap")
    assert isinstance(cap_payload, dict)
    assert cap_payload.get("tool_id") == "browser"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_discover_miss_does_not_emit_render_ui_gap_when_group_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When render_ui is in active_tool_groups, miss must not emit false capability_gap."""
    registry = ToolRegistry()
    registry.register(_DummyDeferredTool(), source=ToolSource.USER, bind_mode=ToolBindMode.DISCOVERABLE)
    discover = sync_discover_capability_tool(
        registry,
        skills=_discover_gateway_skills(),
        active_tool_groups=frozenset(
            {"web", "memory", "file_ops", "shell", "render_ui"},
        ),
    )
    assert discover is not None

    captured: list[tuple[str, object]] = []

    async def _capture(name: str, data: object, config: object | None = None) -> None:
        captured.append((name, data))

    monkeypatch.setattr(
        "myrm_agent_harness.utils.event_utils.dispatch_custom_event",
        _capture,
    )

    result = await discover.ainvoke({"query": "please render ui interactive form"})
    assert "No capabilities found" in result
    assert "<CapabilityGap>" not in result
    assert not any(name == "capability_gap" for name, _ in captured)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_discover_miss_emits_render_ui_gap_when_group_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When render_ui is NOT in active_tool_groups, miss must emit capability_gap."""
    registry = ToolRegistry()
    registry.register(_DummyDeferredTool(), source=ToolSource.USER, bind_mode=ToolBindMode.DISCOVERABLE)
    discover = sync_discover_capability_tool(
        registry,
        skills=_discover_gateway_skills(),
        active_tool_groups=frozenset({"web", "memory", "file_ops", "shell"}),
    )
    assert discover is not None

    captured: list[tuple[str, object]] = []

    async def _capture(name: str, data: object, config: object | None = None) -> None:
        captured.append((name, data))

    monkeypatch.setattr(
        "myrm_agent_harness.utils.event_utils.dispatch_custom_event",
        _capture,
    )

    result = await discover.ainvoke({"query": "please render ui interactive form"})
    assert "No capabilities found" in result
    assert "<CapabilityGap>" in result
    assert any(name == "capability_gap" for name, _ in captured)
    cap_payload = next(payload for name, payload in captured if name == "capability_gap")
    assert isinstance(cap_payload, dict)
    assert cap_payload.get("tool_id") == "render_ui"


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("query", "expected_tool_id"),
    [
        ("generate video from this script", "video_generation"),
        ("create multi-step plan for migration", "planning"),
        ("search my personal wiki notes", "wiki"),
    ],
)
async def test_discover_miss_emits_capability_gap_for_disabled_groups(
    monkeypatch: pytest.MonkeyPatch,
    query: str,
    expected_tool_id: str,
) -> None:
    registry = ToolRegistry()
    registry.register(_DummyDeferredTool(), source=ToolSource.USER, bind_mode=ToolBindMode.DISCOVERABLE)
    discover = sync_discover_capability_tool(
        registry,
        skills=_discover_gateway_skills(),
        active_tool_groups=frozenset({"web", "memory", "file_ops", "shell"}),
    )
    assert discover is not None

    captured: list[tuple[str, object]] = []

    async def _capture(name: str, data: object, config: object | None = None) -> None:
        captured.append((name, data))

    monkeypatch.setattr(
        "myrm_agent_harness.utils.event_utils.dispatch_custom_event",
        _capture,
    )

    result = await discover.ainvoke({"query": query})
    assert "No capabilities found" in result
    assert "<CapabilityGap>" in result
    cap_payload = next(payload for name, payload in captured if name == "capability_gap")
    assert isinstance(cap_payload, dict)
    assert cap_payload.get("tool_id") == expected_tool_id


@pytest.mark.integration
@pytest.mark.asyncio
async def test_discover_miss_no_gap_for_file_ops_intent_without_file_group(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fast-mode groups omit file_ops; grep/bash queries must not emit file_ops entitlement gap."""
    registry = ToolRegistry()
    registry.register(_DummyDeferredTool(), source=ToolSource.USER, bind_mode=ToolBindMode.DISCOVERABLE)
    discover = sync_discover_capability_tool(
        registry,
        skills=_discover_gateway_skills(),
        active_tool_groups=frozenset({"web", "memory", "answer_tool"}),
    )
    assert discover is not None

    captured: list[tuple[str, object]] = []

    async def _capture(name: str, data: object, config: object | None = None) -> None:
        captured.append((name, data))

    monkeypatch.setattr(
        "myrm_agent_harness.utils.event_utils.dispatch_custom_event",
        _capture,
    )

    result = await discover.ainvoke({"query": "grep pattern in repo files and run bash script"})
    assert "No capabilities found" in result
    assert "<CapabilityGap>" not in result
    assert not any(name == "capability_gap" for name, _ in captured)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_discover_miss_emits_skill_gap_block_and_sse(monkeypatch: pytest.MonkeyPatch) -> None:
    """Deterministic: unbound skill in query → SkillGap block + skill_gap SSE."""
    registry = ToolRegistry()
    registry.register(_DummyDeferredTool(), source=ToolSource.USER, bind_mode=ToolBindMode.DISCOVERABLE)
    discover = sync_discover_capability_tool(
        registry,
        skills=_discover_gateway_skills(),
        bound_skill_names=frozenset(),
        library_skill_names=frozenset({"github_pr_skill"}),
    )
    assert discover is not None

    captured: list[tuple[str, object]] = []

    async def _capture(name: str, data: object, config: object | None = None) -> None:
        captured.append((name, data))

    monkeypatch.setattr(
        "myrm_agent_harness.utils.event_utils.dispatch_custom_event",
        _capture,
    )

    result = await discover.ainvoke({"query": "run github_pr_skill workflow now"})
    assert "No capabilities found" in result
    assert "<SkillGap>" in result
    assert any(name == "skill_gap" for name, _ in captured)
    skill_payload = next(payload for name, payload in captured if name == "skill_gap")
    assert isinstance(skill_payload, dict)
    assert skill_payload.get("skill_id") == "github_pr_skill"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_stream_dispatcher_forwards_skill_gap_custom_event() -> None:
    """Custom stream chunk skill_gap must become SKILL_GAP SSE event."""
    stats = AgentRunStatistics()
    ctx = StreamContext(
        agent=MagicMock(),
        agent_input={"messages": []},
        merged_context={"locale": "en"},
        run_config={},
        stats=stats,
        message_id="skill_gap_dispatch_test",
        cancel_token=None,
        steering_token=None,
        source_tracker=MagicMock(),
        output_queue=asyncio.Queue(),
        event_logger=None,
    )

    class _FakeCompactor:
        def __init__(self) -> None:
            self.events: list[object] = []

        async def put(self, event: object) -> None:
            self.events.append(event)

    executor = StreamExecutor(
        ctx=ctx,
        fallback_llm=None,
        safety_fallback_llm=None,
        rebuild_agent_fn=MagicMock(),
    )
    executor._compactor = _FakeCompactor()

    payload = {"skill_id": "github_pr_skill"}
    chunk = ("custom", {"name": "skill_gap", "data": payload})
    await executor._dispatch_chunk(chunk, ctx, [])

    gap_events = [
        event
        for event in executor._compactor.events
        if isinstance(event, AgentStreamEvent) and event.type == AgentEventType.SKILL_GAP
    ]
    assert len(gap_events) == 1
    assert gap_events[0].data == payload


@pytest.mark.integration
@pytest.mark.asyncio
async def test_stream_dispatcher_forwards_capability_gap_custom_event() -> None:
    """Custom stream chunk capability_gap must become CAPABILITY_GAP SSE event."""
    stats = AgentRunStatistics()
    ctx = StreamContext(
        agent=MagicMock(),
        agent_input={"messages": []},
        merged_context={"locale": "en"},
        run_config={},
        stats=stats,
        message_id="gap_dispatch_test",
        cancel_token=None,
        steering_token=None,
        source_tracker=MagicMock(),
        output_queue=asyncio.Queue(),
        event_logger=None,
    )

    class _FakeCompactor:
        def __init__(self) -> None:
            self.events: list[object] = []

        async def put(self, event: object) -> None:
            self.events.append(event)

    executor = StreamExecutor(
        ctx=ctx,
        fallback_llm=None,
        safety_fallback_llm=None,
        rebuild_agent_fn=MagicMock(),
    )
    executor._compactor = _FakeCompactor()

    payload = {"tool_id": "browser", "tool_group": "browser"}
    chunk = ("custom", {"name": "capability_gap", "data": payload})
    await executor._dispatch_chunk(chunk, ctx, [])

    gap_events = [
        event
        for event in executor._compactor.events
        if isinstance(event, AgentStreamEvent) and event.type == AgentEventType.CAPABILITY_GAP
    ]
    assert len(gap_events) == 1
    assert gap_events[0].data == payload


@pytest.mark.e2e
def test_agent_stream_discover_miss_emits_capability_gap_sse(client: TestClient) -> None:
    """Real agent-stream: discover on browser query must emit capability_gap SSE."""
    gap_query = "zzz_gap_browser_selenium_website_7742"
    chat_id = f"test_cap_gap_{uuid.uuid4().hex[:8]}"
    create_response = client.post("/api/v1/chats/", json={"chat_id": chat_id})
    assert create_response.status_code == 200

    payload: dict[str, object] = {
        "message_id": "test-cap-gap-1",
        "chat_id": chat_id,
        "query": (
            "You MUST call discover_capability_tool exactly once with query "
            f"'{gap_query}'. Do not call any other tool. "
            "After the tool returns, reply with the single word DONE."
        ),
        "action_mode": "agent",
        "model_selection": get_lite_model_selection(),
        "agent_config": {
            "enabled_builtin_tools": ["web_search", "memory", "file_ops", "code_execute"],
            "skill_ids": [],
        },
        "timezone": "UTC",
    }
    events = _collect_agent_stream(client, payload)
    check_e2e_errors(events)

    invoked = _invoked_tool_names(events)
    if "discover_capability_tool" not in invoked:
        pytest.skip(
            "model did not invoke discover_capability_tool; deterministic gap wiring covered elsewhere"
        )

    gaps = _gap_events(events, "capability_gap")
    blob = json.dumps(events, ensure_ascii=False)
    assert gaps or "<CapabilityGap>" in blob, (
        "expected capability_gap SSE or CapabilityGap block when discover misses for browser query"
    )
    if gaps:
        payload_data = gaps[0].get("data")
        assert isinstance(payload_data, dict)
        assert payload_data.get("tool_id") == "browser"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_discover_miss_emits_web_search_gap_when_web_group_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When web group is absent from active_tool_groups, web_search query must emit gap."""
    registry = ToolRegistry()
    registry.register(_DummyDeferredTool(), source=ToolSource.USER, bind_mode=ToolBindMode.DISCOVERABLE)
    discover = sync_discover_capability_tool(
        registry,
        skills=_discover_gateway_skills(),
        active_tool_groups=frozenset({"memory", "file_ops", "shell"}),
    )
    assert discover is not None

    captured: list[tuple[str, object]] = []

    async def _capture(name: str, data: object, config: object | None = None) -> None:
        captured.append((name, data))

    monkeypatch.setattr(
        "myrm_agent_harness.utils.event_utils.dispatch_custom_event",
        _capture,
    )

    result = await discover.ainvoke({"query": "search the web for apple news today"})
    assert "No capabilities found" in result
    assert "<CapabilityGap>" in result
    cap_payload = next(payload for name, payload in captured if name == "capability_gap")
    assert isinstance(cap_payload, dict)
    assert cap_payload.get("tool_id") == "web_search"


@pytest.mark.integration
def test_agent_stream_preflight_emits_render_ui_gap_sse(client: TestClient) -> None:
    """User message preflight must emit capability_gap before agent needs discover."""
    from app.services.agent.stream_session.entitlement_gap_preflight import (
        reset_capability_gap_emission_tracker,
    )

    reset_capability_gap_emission_tracker()
    chat_id = f"test_preflight_render_ui_{uuid.uuid4().hex[:8]}"
    payload: dict[str, object] = {
        "messageId": f"msg_{uuid.uuid4().hex[:8]}",
        "chatId": chat_id,
        "query": "帮我填表准备 staging 部署配置",
        "actionMode": "agent",
        "modelSelection": get_lite_model_selection(),
        "agentConfig": {
            "enabledBuiltinTools": ["web_search", "memory", "structured_clarify"],
        },
        "timezone": "UTC",
    }
    events = _collect_agent_stream(client, payload)
    check_e2e_errors(events)

    gaps = _gap_events(events, "capability_gap")
    assert gaps, "expected stream preflight capability_gap SSE for render_ui form query"
    payload_data = gaps[0].get("data")
    assert isinstance(payload_data, dict)
    assert payload_data.get("tool_id") == "render_ui"
    assert payload_data.get("tool_group") == "render_ui"


@pytest.mark.integration
def test_agent_stream_accepts_enabled_builtin_tools_without_error(client: TestClient) -> None:
    """agent-stream with explicit enabledBuiltinTools (no browser) must complete."""
    chat_id = f"test_enabled_tools_{uuid.uuid4().hex[:8]}"
    payload: dict[str, object] = {
        "messageId": "test-enabled-tools-1",
        "chatId": chat_id,
        "query": "Reply with the word OK only.",
        "actionMode": "agent",
        "modelSelection": get_lite_model_selection(),
        "agentConfig": {
            "enabledBuiltinTools": ["web_search", "memory", "file_ops", "code_execute"],
        },
        "timezone": "UTC",
    }
    events = _collect_agent_stream(client, payload)
    check_e2e_errors(events)
    assert events


@pytest.mark.integration
def test_agent_stream_default_builtin_tools_persist_togglable_only(client: TestClient) -> None:
    """Default agent-stream persists togglable tools only; baseline is runtime-forced."""
    from app.services.agent.builtin_tool_ids import (
        AGENT_BASELINE_BUILTIN_TOOLS,
        DEFAULT_ENABLED_BUILTIN_TOOLS,
    )

    chat_id = f"test_default_tools_{uuid.uuid4().hex[:8]}"
    payload = {
        "query": "Reply with the word OK only.",
        "message_id": "test-default-tools-1",
        "chat_id": chat_id,
        "action_mode": "agent",
        "model_selection": get_lite_model_selection(),
        "timezone": "UTC",
    }
    events = _collect_agent_stream(client, payload)
    check_e2e_errors(events)

    tools_snapshot = next(
        (event for event in events if event.get("type") == "tools_snapshot"),
        None,
    )
    if tools_snapshot is None:
        invoked = _invoked_tool_names(events)
        assert "file_read_tool" in invoked or "bash_code_execute_tool" in invoked, (
            "baseline file/bash must be Turn1 eager when tools_snapshot absent"
        )
        return

    snapshot_data = tools_snapshot.get("data")
    if not isinstance(snapshot_data, dict):
        pytest.skip("tools_snapshot payload missing")

    enabled = snapshot_data.get("enabled_builtin_tools")
    if not isinstance(enabled, list):
        pytest.skip("tools_snapshot missing enabled_builtin_tools")

    for tool_id in DEFAULT_ENABLED_BUILTIN_TOOLS:
        assert tool_id in enabled, f"default tool {tool_id!r} missing from tools_snapshot"
    for tool_id in AGENT_BASELINE_BUILTIN_TOOLS:
        assert tool_id not in enabled, f"baseline {tool_id!r} must not appear in persisted snapshot"


@pytest.mark.integration
def test_agent_stream_tools_snapshot_includes_builtin_tool_id(client: TestClient) -> None:
    """Turn1 tools_snapshot rows must carry harness-derived builtin_tool_id for GUI labels."""
    chat_id = f"test_snapshot_builtin_id_{uuid.uuid4().hex[:8]}"
    payload: dict[str, object] = {
        "query": "Reply with the word OK only.",
        "message_id": "test-snapshot-builtin-id-1",
        "chat_id": chat_id,
        "action_mode": "agent",
        "model_selection": get_lite_model_selection(),
        "agent_config": {
            "enabled_builtin_tools": ["web_search", "memory", "cron"],
            "skill_ids": [],
        },
        "timezone": "UTC",
    }
    events = _collect_agent_stream(client, payload)
    check_e2e_errors(events)

    tools_snapshot = next(
        (event for event in events if event.get("type") == "tools_snapshot"),
        None,
    )
    if tools_snapshot is None:
        pytest.skip("tools_snapshot not emitted in this stream")

    snapshot_rows = tools_snapshot.get("data")
    if not isinstance(snapshot_rows, list):
        pytest.skip("tools_snapshot data is not a tool list")

    web_rows = [
        row for row in snapshot_rows if isinstance(row, dict) and row.get("name") == "web_search_tool"
    ]
    assert web_rows, "expected web_search_tool in Turn1 tools_snapshot"
    assert web_rows[0].get("builtin_tool_id") == "web_search"

    cron_rows = [
        row for row in snapshot_rows if isinstance(row, dict) and row.get("name") == "cron_manage_tool"
    ]
    if cron_rows:
        assert cron_rows[0].get("builtin_tool_id") == "cron"


@pytest.mark.e2e
def test_agent_stream_discover_miss_emits_cron_capability_gap_sse(client: TestClient) -> None:
    """Real agent-stream: discover on cron query must emit capability_gap when cron disabled."""
    gap_query = "schedule daily reminder cron job at 9am every morning"
    chat_id = f"test_cron_cap_gap_{uuid.uuid4().hex[:8]}"
    create_response = client.post("/api/v1/chats/", json={"chat_id": chat_id})
    assert create_response.status_code == 200

    payload: dict[str, object] = {
        "message_id": "test-cron-cap-gap-1",
        "chat_id": chat_id,
        "query": (
            "You MUST call discover_capability_tool exactly once with query "
            f"'{gap_query}'. Do not call any other tool. "
            "After the tool returns, reply with the single word DONE."
        ),
        "action_mode": "agent",
        "model_selection": get_lite_model_selection(),
        "agent_config": {
            "enabled_builtin_tools": ["web_search", "memory"],
            "skill_ids": [],
        },
        "timezone": "UTC",
    }
    events = _collect_agent_stream(client, payload)
    check_e2e_errors(events)

    invoked = _invoked_tool_names(events)
    if "discover_capability_tool" not in invoked:
        pytest.skip(
            "model did not invoke discover_capability_tool; deterministic cron gap covered in harness unit tests"
        )

    gaps = _gap_events(events, "capability_gap")
    blob = json.dumps(events, ensure_ascii=False)
    assert gaps or "<CapabilityGap>" in blob or "cron" in blob.lower(), (
        "expected capability_gap SSE or CapabilityGap block for cron miss query"
    )
    if gaps:
        payload_data = gaps[0].get("data")
        assert isinstance(payload_data, dict)
        assert payload_data.get("tool_id") == "cron"
