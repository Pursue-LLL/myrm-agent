"""Unit tests for StreamContentCollector UI artifact collection."""

import pytest

from app.services.agent.streaming_support.stream_collector import StreamContentCollector


@pytest.fixture
def collector() -> StreamContentCollector:
    return StreamContentCollector(chat_id="test_chat", sibling_group_id="sib_1")


class TestUIArtifactCollection:
    """Tests for ui_update event collection in StreamContentCollector."""

    def test_collects_ui_artifact_events(self, collector: StreamContentCollector) -> None:
        collector.feed_event({
            "type": "ui_update",
            "subtype": "ui_artifact",
            "data": [
                {
                    "surface_id": "form_1",
                    "title": "Travel Form",
                    "components": [],
                    "root_ids": [],
                    "data": {"destination": ""},
                    "actions": [],
                },
            ],
            "messageId": "msg_1",
        })

        extra = collector.extra_data
        assert extra is not None
        assert "uiArtifacts" in extra
        assert len(extra["uiArtifacts"]) == 1
        assert extra["uiArtifacts"][0]["surface_id"] == "form_1"

    def test_merges_data_update_into_existing_artifact(
        self, collector: StreamContentCollector
    ) -> None:
        collector.feed_event({
            "type": "ui_update",
            "subtype": "ui_artifact",
            "data": [
                {
                    "surface_id": "form_1",
                    "title": "Form",
                    "components": [],
                    "root_ids": [],
                    "data": {"name": "", "age": 0},
                    "actions": [],
                },
            ],
            "messageId": "msg_1",
        })

        collector.feed_event({
            "type": "ui_update",
            "subtype": "data_update",
            "data": {"surface_id": "form_1", "updates": {"name": "Alice", "age": 30}},
            "messageId": "msg_1",
        })

        extra = collector.extra_data
        assert extra is not None
        artifact = extra["uiArtifacts"][0]
        assert artifact["data"]["name"] == "Alice"
        assert artifact["data"]["age"] == 30

    def test_deep_merges_nested_data_update_without_wiping_sibling_fields(
        self, collector: StreamContentCollector
    ) -> None:
        collector.feed_event({
            "type": "ui_update",
            "subtype": "ui_artifact",
            "data": [
                {
                    "surface_id": "form_nested",
                    "title": "Form",
                    "components": [],
                    "root_ids": [],
                    "data": {"form": {"note": "", "env": "staging"}},
                    "actions": [],
                },
            ],
            "messageId": "msg_nested",
        })

        collector.feed_event({
            "type": "ui_update",
            "subtype": "data_update",
            "data": {"surface_id": "form_nested", "updates": {"form": {"note": "done"}}},
            "messageId": "msg_nested",
        })

        extra = collector.extra_data
        assert extra is not None
        assert extra["uiArtifacts"][0]["data"] == {
            "form": {"note": "done", "env": "staging"},
        }

    def test_data_update_for_unknown_surface_id_is_ignored(
        self, collector: StreamContentCollector
    ) -> None:
        collector.feed_event({
            "type": "ui_update",
            "subtype": "data_update",
            "data": {"surface_id": "nonexistent", "updates": {"key": "val"}},
            "messageId": "msg_1",
        })

        assert collector.extra_data is None

    def test_multiple_artifacts_collected(self, collector: StreamContentCollector) -> None:
        collector.feed_event({
            "type": "ui_update",
            "subtype": "ui_artifact",
            "data": [
                {"surface_id": "a", "title": "A", "components": [], "root_ids": [], "data": {}, "actions": []},
                {"surface_id": "b", "title": "B", "components": [], "root_ids": [], "data": {}, "actions": []},
            ],
            "messageId": "msg_1",
        })

        extra = collector.extra_data
        assert extra is not None
        assert len(extra["uiArtifacts"]) == 2

    def test_snapshot_includes_ui_artifacts(self, collector: StreamContentCollector) -> None:
        collector.feed_event({
            "type": "ui_update",
            "subtype": "ui_artifact",
            "data": [
                {"surface_id": "s1", "title": "S", "components": [], "root_ids": [], "data": {"x": 1}, "actions": []},
            ],
            "messageId": "msg_1",
        })

        snapshot = collector.get_snapshot()
        assert "ui_artifacts" in snapshot
        assert len(snapshot["ui_artifacts"]) == 1
        assert snapshot["ui_artifacts"][0]["data"]["x"] == 1

    def test_snapshot_empty_when_no_artifacts(self, collector: StreamContentCollector) -> None:
        snapshot = collector.get_snapshot()
        assert snapshot["ui_artifacts"] == []

    def test_invalid_data_types_ignored(self, collector: StreamContentCollector) -> None:
        collector.feed_event({
            "type": "ui_update",
            "subtype": "ui_artifact",
            "data": "not_a_list",
            "messageId": "msg_1",
        })

        collector.feed_event({
            "type": "ui_update",
            "subtype": "data_update",
            "data": "not_a_dict",
            "messageId": "msg_1",
        })

        assert collector.extra_data is None
