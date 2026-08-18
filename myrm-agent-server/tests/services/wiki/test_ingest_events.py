"""Tests for wiki ingest SSE event bus."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from myrm_agent_harness.toolkits.wiki.pipeline.resilience import CompileRunSnapshot

from app.services.wiki.ingest_events import (
    WikiIngestEventBus,
    _concepts_tree_fingerprint,
    build_wiki_tree_fingerprint,
    publish_wiki_ingest_snapshot,
)


def _snapshot(
    *, pending: int = 0, processing: int = 0, failed: int = 0
) -> dict[str, object]:
    return {
        "agent_id": None,
        "stats": {
            "pending": pending,
            "processing": processing,
            "completed": 0,
            "failed": failed,
        },
        "compile_run": {
            "state": "running",
            "pause_reason": "",
            "primary_error_kind": "",
        },
    }


@pytest.mark.asyncio
async def test_emit_deduplicates_identical_snapshots() -> None:
    bus = WikiIngestEventBus(poll_interval_seconds=60.0)
    queue = bus.subscribe("__default__")
    snapshot = _snapshot(pending=2)

    await bus.emit("__default__", snapshot)
    await bus.emit("__default__", snapshot)

    assert queue.qsize() == 1


@pytest.mark.asyncio
async def test_emit_marks_sync_required_when_subscriber_queue_full() -> None:
    bus = WikiIngestEventBus(poll_interval_seconds=60.0)
    queue: asyncio.Queue[dict[str, object]] = asyncio.Queue(maxsize=1)
    bus._subscribers["__default__"] = {queue}
    queue.put_nowait(_snapshot(pending=1))

    await bus.emit("__default__", _snapshot(pending=2))

    assert queue.qsize() == 1
    payload = queue.get_nowait()
    assert payload.get("sync_required") is True
    assert payload["stats"] == {
        "pending": 2,
        "processing": 0,
        "completed": 0,
        "failed": 0,
    }


@pytest.mark.asyncio
async def test_publish_wiki_ingest_snapshot_is_best_effort() -> None:
    mock_queue = MagicMock()
    mock_queue.get_stats.side_effect = RuntimeError("queue unavailable")
    mock_archiver = MagicMock()
    mock_archiver._queue = mock_queue

    await publish_wiki_ingest_snapshot(mock_archiver, agent_id=None)


@pytest.mark.asyncio
async def test_scope_poll_is_shared_across_subscribers() -> None:
    bus = WikiIngestEventBus(poll_interval_seconds=60.0)
    mock_archiver = MagicMock()
    mock_queue = MagicMock()
    mock_queue.get_stats.return_value = {
        "pending": 0,
        "processing": 0,
        "completed": 0,
        "failed": 0,
    }
    mock_queue.get_compile_run.return_value = CompileRunSnapshot(state="running")
    mock_archiver._queue = mock_queue

    bus._acquire_scope_poll("__default__", mock_archiver, None)
    bus._acquire_scope_poll("__default__", mock_archiver, None)
    poll_state = bus._scope_polls["__default__"]
    assert poll_state.refs == 2
    first_task = poll_state.poll_task
    assert first_task is not None

    bus._acquire_scope_poll("__default__", mock_archiver, None)
    assert bus._scope_polls["__default__"].poll_task is first_task

    await bus._release_scope_poll("__default__")
    assert bus._scope_polls["__default__"].refs == 2
    await bus._release_scope_poll("__default__")
    await bus._release_scope_poll("__default__")
    assert "__default__" not in bus._scope_polls


@pytest.mark.asyncio
async def test_prepare_snapshot_sets_tree_sync_required_on_tree_change() -> None:
    bus = WikiIngestEventBus(poll_interval_seconds=60.0)
    mock_archiver = MagicMock()

    with patch(
        "app.services.wiki.ingest_events.build_wiki_tree_fingerprint",
        side_effect=["tree-fp-1", "tree-fp-2"],
    ):
        first = bus.prepare_snapshot("__default__", mock_archiver, None)
        assert "tree_sync_required" not in first

        second = bus.prepare_snapshot("__default__", mock_archiver, None)
        assert second.get("tree_sync_required") is True


def test_prepare_snapshot_invalidates_structural_cache_on_tree_change() -> None:
    bus = WikiIngestEventBus(poll_interval_seconds=60.0)
    mock_archiver = MagicMock()
    mock_structure = MagicMock()
    mock_archiver._structure = mock_structure

    with (
        patch(
            "app.services.wiki.ingest_events.build_wiki_tree_fingerprint",
            side_effect=["tree-fp-1", "tree-fp-2"],
        ),
        patch(
            "app.services.wiki.structural_stats_cache.invalidate_structural_lint_cache",
        ) as invalidate_mock,
    ):
        bus.prepare_snapshot("__default__", mock_archiver, None)
        bus.prepare_snapshot("__default__", mock_archiver, None)

    invalidate_mock.assert_called_once_with(mock_structure)


def test_build_wiki_tree_fingerprint_tracks_stale_and_queue_stats() -> None:
    mock_archiver = MagicMock()
    mock_queue = MagicMock()
    mock_queue.get_stats.return_value = {
        "pending": 1,
        "processing": 2,
        "completed": 3,
        "failed": 4,
    }
    mock_archiver._queue = mock_queue
    mock_archiver._structure = MagicMock()

    with (
        patch(
            "myrm_agent_harness.toolkits.wiki.maintenance.stale_summary.collect_stale_raw_files",
            return_value=MagicMock(last_compile_time="2026-07-28T00:00:00+00:00"),
        ),
        patch(
            "myrm_agent_harness.toolkits.wiki.maintenance.stale_summary.collect_stale_raw_path_set",
            return_value=frozenset({"raw/a.md", "raw/b.md"}),
        ),
        patch(
            "app.services.wiki.ingest_events._concepts_tree_fingerprint",
            return_value="concepts-fp",
        ),
    ):
        fingerprint = build_wiki_tree_fingerprint(mock_archiver)

    assert '"completed":3' in fingerprint
    assert '"failed":4' in fingerprint
    assert '"stale_count":2' in fingerprint
    assert "2026-07-28T00:00:00+00:00" in fingerprint
    assert '"concepts":"concepts-fp"' in fingerprint


def test_concepts_tree_fingerprint_tracks_compiled_page_changes(tmp_path: Path) -> None:
    from myrm_agent_harness.toolkits.wiki.core.structure import WikiStructure

    structure = WikiStructure(tmp_path)
    structure.ensure_structure()
    concept = structure.get_concept_file_path("research/react-hooks")
    concept.write_text("# React Hooks\n\nCompiled truth.", encoding="utf-8")

    first = _concepts_tree_fingerprint(structure)
    assert first != ""

    concept.write_text("# React Hooks\n\nUpdated compiled truth.", encoding="utf-8")
    second = _concepts_tree_fingerprint(structure)
    assert second != first


def test_concepts_tree_fingerprint_excludes_sidecar_and_public_mounts(
    tmp_path: Path,
) -> None:
    from myrm_agent_harness.toolkits.wiki.core.structure import WikiStructure

    public_dir = tmp_path / "public"
    structure = WikiStructure(tmp_path, public_dirs=[public_dir])
    structure.ensure_structure()

    concept = structure.get_concept_file_path("research/react-hooks")
    concept.write_text("# React Hooks\n\nCompiled truth.", encoding="utf-8")

    abstract, overview = structure.get_directory_sidecar_paths("research")
    abstract.write_text("# Abstract", encoding="utf-8")
    overview.write_text("# Overview", encoding="utf-8")

    public_concept = public_dir / "wiki" / "concepts" / "public-page.md"
    public_concept.parent.mkdir(parents=True, exist_ok=True)
    public_concept.write_text("# Public", encoding="utf-8")

    fingerprint = _concepts_tree_fingerprint(structure)
    assert "react-hooks" in fingerprint
    assert ".abstract" not in fingerprint
    assert ".overview" not in fingerprint
    assert "public-page" not in fingerprint


def test_concepts_tree_fingerprint_handles_missing_dir_and_non_structure() -> None:
    from myrm_agent_harness.toolkits.wiki.core.structure import WikiStructure

    structure = WikiStructure("/nonexistent/path")
    assert _concepts_tree_fingerprint(structure) == ""

    assert _concepts_tree_fingerprint(object()) == ""


def test_concepts_tree_fingerprint_tracks_add_and_delete(tmp_path: Path) -> None:
    from myrm_agent_harness.toolkits.wiki.core.structure import WikiStructure

    structure = WikiStructure(tmp_path)
    structure.ensure_structure()
    concept = structure.get_concept_file_path("research/react-hooks")
    concept.write_text("# React Hooks", encoding="utf-8")

    base = _concepts_tree_fingerprint(structure)

    added = structure.get_concept_file_path("research/new-topic")
    added.write_text("# New Topic", encoding="utf-8")
    assert _concepts_tree_fingerprint(structure) != base

    added.unlink()
    assert _concepts_tree_fingerprint(structure) == base


@pytest.mark.asyncio
async def test_publish_wiki_ingest_snapshot_sets_stats_refresh_required() -> None:
    bus = WikiIngestEventBus(poll_interval_seconds=60.0)
    queue = bus.subscribe("agent-a")
    mock_archiver = MagicMock()
    mock_queue = MagicMock()
    mock_queue.get_stats.return_value = {
        "pending": 0,
        "processing": 0,
        "completed": 0,
        "failed": 0,
    }
    mock_queue.get_compile_run.return_value = CompileRunSnapshot(state="running")
    mock_archiver._queue = mock_queue
    mock_archiver._structure = MagicMock()
    mock_archiver._pending_mgr = MagicMock()
    mock_archiver._pending_mgr.count_synthesis_pending.return_value = 0

    with (
        patch("app.services.wiki.ingest_events.wiki_ingest_event_bus", bus),
        patch(
            "app.services.wiki.ingest_events.build_wiki_tree_fingerprint",
            return_value="tree-fp-stats-refresh",
        ),
    ):
        await publish_wiki_ingest_snapshot(
            mock_archiver,
            agent_id="agent-a",
            stats_refresh_required=True,
        )

    payload = queue.get_nowait()
    assert payload.get("stats_refresh_required") is True
