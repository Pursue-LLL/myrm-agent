"""Deterministic integration: render_ui → UI registry → collect_ui_artifacts → SSE collector."""

from __future__ import annotations

import asyncio

import pytest

from app.services.agent.streaming_support.stream_collector import StreamContentCollector
from myrm_agent_harness.agent._internals.run_lifecycle import post_run_events
from myrm_agent_harness.agent.artifacts.context import ArtifactContextManager
from myrm_agent_harness.agent.artifacts.ui_registry import (
    bind_run_message_id,
    pop_pending_ui_events_for_message,
    pop_run_message_id,
)
from myrm_agent_harness.agent.meta_tools.interaction.render_ui_tool import render_ui
from myrm_agent_harness.agent.streaming.artifact_events import collect_ui_artifacts
from myrm_agent_harness.agent.streaming.types import AgentEventType
from myrm_agent_harness.agent.types import AgentRunStatistics


@pytest.fixture
def run_bind_session() -> tuple[str, str]:
    """Simulate agent_runtime bind_run_message_id; always pop on teardown."""
    session_key = "chat_integration_bind"
    message_id = "msg_run_bind_integration"
    bind_run_message_id(session_key, message_id)
    yield session_key, message_id
    pop_run_message_id(session_key)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_post_run_collects_ui_stashed_from_child_task() -> None:
    """StreamExecutor runs in asyncio.create_task; UI must survive ContextVar copy."""
    import asyncio

    from myrm_agent_harness.agent._internals.run_lifecycle import post_run_events
    from myrm_agent_harness.agent.artifacts.context import ArtifactContextManager
    from myrm_agent_harness.agent.meta_tools.interaction.render_ui_tool import render_ui
    from myrm_agent_harness.agent.streaming.types import AgentEventType
    from myrm_agent_harness.agent.types import AgentRunStatistics

    async def simulate_tool_in_executor_task() -> None:
        with ArtifactContextManager(message_id="msg_child_task"):
            render_ui(
                title="部署确认",
                components=[{"id": "t1", "type": "text", "props": {"text": "ok"}}],
                root_ids=["t1"],
            )

    with ArtifactContextManager(message_id="msg_child_task"):
        await asyncio.create_task(simulate_tool_in_executor_task())
        stats = AgentRunStatistics()
        events = [event async for event in post_run_events(stats, "msg_child_task", {}, False, None)]

    ui_events = [event for event in events if event.get("type") == AgentEventType.UI_UPDATE.value]
    assert len(ui_events) == 1
    assert ui_events[0].get("subtype") == "ui_artifact"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_collect_ui_artifacts_emits_ui_update_after_render_ui() -> None:
    """render_ui registers UIArtifact; collect_ui_artifacts must emit ui_update SSE payload."""
    with ArtifactContextManager():
        render_ui(
            title="部署确认",
            components=[
                {"id": "t1", "type": "text", "props": {"text": "确认重启 staging?"}},
                {
                    "id": "f1",
                    "type": "text_field",
                    "props": {"label": "备注"},
                    "bindings": {"value": "$.form.note"},
                },
                {
                    "id": "b1",
                    "type": "button",
                    "props": {"label": "确认"},
                    "events": {"onClick": "submit"},
                },
            ],
            root_ids=["t1", "f1", "b1"],
            data={"form": {"note": ""}},
            actions=[{"id": "submit", "type": "submit", "label": "确认"}],
        )

        events = [event async for event in collect_ui_artifacts("msg_render_ui_wiring")]

    assert len(events) == 1
    ui_event = events[0]
    assert ui_event["type"] == AgentEventType.UI_UPDATE.value
    assert ui_event["subtype"] == "ui_artifact"
    assert ui_event["messageId"] == "msg_render_ui_wiring"

    data = ui_event["data"]
    assert isinstance(data, list) and len(data) == 1
    artifact = data[0]
    assert isinstance(artifact, dict)
    assert artifact.get("title") == "部署确认"
    assert len(artifact.get("components", [])) == 3
    assert artifact.get("root_ids") == ["t1", "f1", "b1"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_post_run_events_forwards_ui_update_before_message_end() -> None:
    """post_run_events must yield ui_update before MESSAGE_END (agent-stream contract)."""
    with ArtifactContextManager():
        render_ui(
            title="Smoke Form",
            components=[
                {"id": "name", "type": "text_field", "props": {"label": "Name"}},
            ],
            root_ids=["name"],
            data={"form": {"name": ""}},
        )

        stats = AgentRunStatistics()
        events = [event async for event in post_run_events(stats, "msg_post_run", {}, False, None)]

    ui_events = [e for e in events if e.get("type") == AgentEventType.UI_UPDATE.value]
    assert len(ui_events) == 1
    assert ui_events[0].get("subtype") == "ui_artifact"
    assert events[-1]["type"] == AgentEventType.MESSAGE_END.value


@pytest.mark.integration
def test_stream_collector_persists_ui_update_from_harness_event() -> None:
    """Server StreamContentCollector must persist ui_update for DB/extra_data."""
    collector = StreamContentCollector(chat_id="chat_ui", sibling_group_id="sib_ui")

    collector.feed_event(
        {
            "type": "ui_update",
            "subtype": "ui_artifact",
            "data": [
                {
                    "surface_id": "form_deploy",
                    "title": "部署确认",
                    "components": [],
                    "root_ids": ["t1"],
                    "data": {"form": {"note": ""}},
                    "actions": [],
                },
            ],
            "messageId": "msg_collector",
        }
    )

    extra = collector.extra_data
    assert extra is not None
    assert extra["uiArtifacts"][0]["title"] == "部署确认"
    snapshot = collector.get_snapshot()
    assert snapshot["ui_artifacts"][0]["surface_id"] == "form_deploy"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_langgraph_tool_task_without_artifact_context_uses_run_bind(
    run_bind_session: tuple[str, str],
) -> None:
    """Production fix: LangGraph tool task has no ArtifactContext; run bind delivers UI."""
    _session_key, message_id = run_bind_session

    async def simulate_langgraph_tool_task() -> str:
        return render_ui(
            title="部署确认",
            components=[{"id": "t1", "type": "text", "props": {"text": "确认重启 staging?"}}],
            root_ids=["t1"],
        )

    result = await asyncio.create_task(simulate_langgraph_tool_task())
    assert "部署确认" in result

    stats = AgentRunStatistics()
    events = [event async for event in post_run_events(stats, message_id, {}, False, None)]
    ui_events = [event for event in events if event.get("type") == AgentEventType.UI_UPDATE.value]
    assert len(ui_events) == 1
    assert ui_events[0].get("subtype") == "ui_artifact"
    assert pop_pending_ui_events_for_message(message_id) == []


@pytest.mark.integration
@pytest.mark.asyncio
async def test_collect_ui_artifacts_via_run_bind_without_artifact_context(
    run_bind_session: tuple[str, str],
) -> None:
    """collect_ui_artifacts must read stashed UI from run bind when ContextVar registry is absent."""
    _session_key, message_id = run_bind_session

    render_ui(
        title="Run Bind Form",
        components=[
            {"id": "note", "type": "text_field", "props": {"label": "备注"}},
        ],
        root_ids=["note"],
        data={"form": {"note": ""}},
    )

    events = [event async for event in collect_ui_artifacts(message_id)]
    assert len(events) == 1
    assert events[0]["type"] == AgentEventType.UI_UPDATE.value
    assert events[0]["messageId"] == message_id
    artifact = events[0]["data"][0]
    assert artifact["title"] == "Run Bind Form"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_type_inference_delivers_ui_via_run_bind(
    run_bind_session: tuple[str, str],
) -> None:
    """LLM often omits type; inference + run bind must still emit ui_update."""
    _session_key, message_id = run_bind_session

    result = render_ui(
        title="类型推断",
        components=[{"id": "t1", "props": {"text": "确认?"}}],
        root_ids=["t1"],
    )
    assert "类型推断" in result

    events = [event async for event in collect_ui_artifacts(message_id)]
    assert len(events) == 1
    components = events[0]["data"][0]["components"]
    assert components[0]["type"] == "text"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_validation_failure_no_ui_stash_or_post_run_sse(
    run_bind_session: tuple[str, str],
) -> None:
    """Invalid component type must fail-closed: no stash, no ui_update in post_run."""
    _session_key, message_id = run_bind_session

    result = render_ui(
        title="Bad UI",
        components=[
            {"id": "valid", "type": "text", "props": {"text": "ok"}},
            {"id": "invalid", "type": "nonexistent_type", "props": {}},
        ],
        root_ids=["valid"],
    )
    assert result.startswith("Failed to render UI")
    assert "nonexistent_type" in result

    collected = [event async for event in collect_ui_artifacts(message_id)]
    assert collected == []

    stats = AgentRunStatistics()
    events = [event async for event in post_run_events(stats, message_id, {}, False, None)]
    ui_events = [event for event in events if event.get("type") == AgentEventType.UI_UPDATE.value]
    assert ui_events == []
    assert events[-1]["type"] == AgentEventType.MESSAGE_END.value


@pytest.mark.integration
@pytest.mark.asyncio
async def test_render_ui_without_bind_or_context_fails_in_child_task() -> None:
    """No ArtifactContext and no run bind → render_ui must not stash UI."""
    pop_run_message_id("")

    async def orphan_tool_task() -> str:
        return render_ui(
            title="Orphan",
            components=[{"id": "t1", "type": "text", "props": {"text": "x"}}],
            root_ids=["t1"],
        )

    result = await asyncio.create_task(orphan_tool_task())
    assert result.startswith("Failed to render UI")
    assert "registry is not initialized" in result


@pytest.mark.integration
@pytest.mark.asyncio
async def test_run_bind_post_run_feeds_stream_collector(
    run_bind_session: tuple[str, str],
) -> None:
    """Full chain: run bind → render_ui → post_run ui_update → StreamContentCollector."""
    _session_key, message_id = run_bind_session

    render_ui(
        title="链路透传",
        components=[{"id": "t1", "type": "text", "props": {"text": "hello"}}],
        root_ids=["t1"],
    )

    stats = AgentRunStatistics()
    harness_events = [event async for event in post_run_events(stats, message_id, {}, False, None)]
    ui_event = next(event for event in harness_events if event.get("type") == AgentEventType.UI_UPDATE.value)

    collector = StreamContentCollector(chat_id="chat_chain", sibling_group_id="sib_chain")
    collector.feed_event(ui_event)

    extra = collector.extra_data
    assert extra is not None
    assert extra["uiArtifacts"][0]["title"] == "链路透传"
    snapshot = collector.get_snapshot()
    assert len(snapshot["ui_artifacts"]) == 1


@pytest.mark.integration
@pytest.mark.asyncio
async def test_adjacency_validation_fail_closed_no_ui_update(
    run_bind_session: tuple[str, str],
) -> None:
    """Missing root_id in adjacency graph must fail-closed with no stash or SSE."""
    _session_key, message_id = run_bind_session

    result = render_ui(
        title="Bad Adjacency",
        components=[{"id": "t1", "type": "text", "props": {"text": "ok"}}],
        root_ids=["missing_root"],
    )
    assert result.startswith("Failed to render UI")

    collected = [event async for event in collect_ui_artifacts(message_id)]
    assert collected == []


@pytest.mark.integration
@pytest.mark.asyncio
async def test_stash_isolated_by_message_id(run_bind_session: tuple[str, str]) -> None:
    """UI stashed for message A must not be delivered when collecting message B."""
    session_key, message_a = run_bind_session
    message_b = "msg_other_turn"

    render_ui(
        title="Isolated",
        components=[{"id": "t1", "type": "text", "props": {"text": "x"}}],
        root_ids=["t1"],
    )

    events_b = [event async for event in collect_ui_artifacts(message_b)]
    assert events_b == []

    events_a = [event async for event in collect_ui_artifacts(message_a)]
    assert len(events_a) == 1
    assert events_a[0]["data"][0]["title"] == "Isolated"
    pop_run_message_id(session_key)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_multiple_render_ui_artifacts_batched_in_one_sse_event(
    run_bind_session: tuple[str, str],
) -> None:
    """Two render_ui calls in one run must batch into a single ui_update payload."""
    _session_key, message_id = run_bind_session

    render_ui(
        title="Form A",
        components=[{"id": "a1", "type": "text", "props": {"text": "A"}}],
        root_ids=["a1"],
    )
    render_ui(
        title="Form B",
        components=[{"id": "b1", "type": "text", "props": {"text": "B"}}],
        root_ids=["b1"],
    )

    events = [event async for event in collect_ui_artifacts(message_id)]
    assert len(events) == 1
    titles = {artifact["title"] for artifact in events[0]["data"]}
    assert titles == {"Form A", "Form B"}


@pytest.mark.integration
@pytest.mark.asyncio
async def test_pop_run_message_id_blocks_orphan_register() -> None:
    """After pop_run_message_id, render_ui without ArtifactContext must fail-closed."""
    pop_run_message_id("")
    bind_run_message_id("chat_pop_test", "msg_pop_test")
    pop_run_message_id("chat_pop_test")

    result = render_ui(
        title="After Pop",
        components=[{"id": "t1", "type": "text", "props": {"text": "x"}}],
        root_ids=["t1"],
    )
    assert result.startswith("Failed to render UI")
    assert pop_pending_ui_events_for_message("msg_pop_test") == []
