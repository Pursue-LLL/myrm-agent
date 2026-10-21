"""Tests for channel executor stream helpers."""

from __future__ import annotations

from app.core.channel_bridge.executor_helpers.stream import (
    ShareableArtifact,
    StreamAccumulator,
    step_to_label,
)


def test_step_to_label_unknown_tool_uses_tool_name() -> None:
    label = step_to_label("custom_tool", {"tool_name": "my_tool", "data": [{"query": "find docs"}]})
    assert label is not None
    assert "my_tool" in label
    assert "find docs" in label


def test_stream_accumulator_deduplicates_sources_by_index() -> None:
    acc = StreamAccumulator()
    acc.add_sources([{"index": 1, "title": "A"}, {"index": 1, "title": "dup"}])
    assert len(acc.sources) == 1


def test_shareable_artifact_namedtuple() -> None:
    artifact = ShareableArtifact(artifact_id="id-1", filename="out.html", artifact_type="html")
    assert artifact.filename == "out.html"
