"""Unit tests for stream_collector UI data deep merge helper."""

from __future__ import annotations

from app.services.agent.streaming_support.stream_collector import _deep_merge_ui_data


class TestDeepMergeUiData:
    def test_merges_top_level_scalars(self) -> None:
        result = _deep_merge_ui_data({"name": "", "age": 0}, {"name": "Alice", "age": 30})
        assert result == {"name": "Alice", "age": 30}

    def test_deep_merges_nested_dicts(self) -> None:
        result = _deep_merge_ui_data(
            {"form": {"note": "", "env": "staging"}},
            {"form": {"note": "done"}},
        )
        assert result == {"form": {"note": "done", "env": "staging"}}

    def test_replaces_arrays_by_key(self) -> None:
        result = _deep_merge_ui_data(
            {"items": [{"title": "A"}]},
            {"items": [{"title": "A"}, {"title": "B"}]},
        )
        assert len(result["items"]) == 2
