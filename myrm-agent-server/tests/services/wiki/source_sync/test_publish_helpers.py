"""Shared source_sync publish helpers: conflict policy passthrough and byte-bounded path segments."""

from __future__ import annotations

from pathlib import Path

import pytest
from myrm_agent_harness.toolkits.wiki import WikiStructure
from myrm_agent_harness.toolkits.wiki.pipeline.raw_gate import RawGateError

from app.services.wiki.source_sync.publish_helpers import (
    RawConflictPolicy,
    publish_source_markdown,
    sanitize_path_segment,
)


async def _publish(structure: WikiStructure, content: str, **kwargs: object):
    return await publish_source_markdown(
        structure,
        relative_path="src/doc.md",
        content=content,
        auto_compile=False,
        compiler_enqueue=None,
        **kwargs,
    )


async def test_default_policy_keeps_the_first_version(tmp_path: Path) -> None:
    structure = WikiStructure(base_dir=tmp_path)
    assert (await _publish(structure, "v1 body")).written

    second = await _publish(structure, "v2 body")

    assert second.conflict_skipped and not second.written
    assert "v1 body" in (tmp_path / "raw" / "src" / "doc.md").read_text(encoding="utf-8")


async def test_supersede_replaces_changed_content_and_skips_identical(tmp_path: Path) -> None:
    structure = WikiStructure(base_dir=tmp_path)
    await _publish(structure, "v1 body")

    replaced = await _publish(
        structure, "v2 body", conflict_policy=RawConflictPolicy.SUPERSEDE, supersede_reason="source updated"
    )
    unchanged = await _publish(
        structure, "v2 body", conflict_policy=RawConflictPolicy.SUPERSEDE, supersede_reason="source updated"
    )

    assert replaced.written and replaced.superseded
    assert unchanged.skipped and not unchanged.written
    assert "v2 body" in (tmp_path / "raw" / "src" / "doc.md").read_text(encoding="utf-8")


async def test_supersede_without_reason_is_rejected(tmp_path: Path) -> None:
    structure = WikiStructure(base_dir=tmp_path)
    await _publish(structure, "v1 body")

    with pytest.raises(RawGateError):
        await _publish(structure, "v2 body", conflict_policy=RawConflictPolicy.SUPERSEDE)


def test_sanitize_keeps_existing_ascii_and_short_cjk_segments() -> None:
    assert sanitize_path_segment("foo bar/baz") == "foo_bar_baz"
    assert sanitize_path_segment("合法文档.md") == "合法文档.md"
    assert sanitize_path_segment("a" * 300) == "a" * 120
    assert sanitize_path_segment("  ") == "item"


def test_sanitize_bounds_long_cjk_titles_below_name_max() -> None:
    segment = sanitize_path_segment("中" * 200)

    assert len(segment.encode()) <= 200
    assert segment == "中" * 66
    assert len(f"{segment}-{'x' * 44}.md".encode()) <= 255
