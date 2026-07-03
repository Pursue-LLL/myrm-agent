"""Deterministic integration: render_ui → UI registry → collect_ui_artifacts → SSE collector."""

from __future__ import annotations

import pytest

from app.services.agent.streaming_support.stream_collector import StreamContentCollector
from myrm_agent_harness.agent._internals.run_lifecycle import post_run_events
from myrm_agent_harness.agent.artifacts.context import ArtifactContextManager
from myrm_agent_harness.agent.meta_tools.interaction.render_ui_tool import render_ui
from myrm_agent_harness.agent.streaming.artifact_events import collect_ui_artifacts
from myrm_agent_harness.agent.streaming.types import AgentEventType
from myrm_agent_harness.agent.types import AgentRunStatistics


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
