"""Deferred auto-compile enqueue: files wait for the dedup scan, duplicates stay out of the compile queue."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest
from myrm_agent_harness.toolkits.wiki import WikiStructure
from myrm_agent_harness.toolkits.wiki.pipeline.corpus_dedup import (
    CorpusDedupGovernor,
    CorpusDedupScanner,
    DispositionAction,
    GroupStatus,
)

from app.services.wiki.source_sync.deferred_enqueue import DeferredCompileEnqueue

SAME_BODY = "# Report\n\nThe very same body, imported twice."
SHARED_NEAR = "the quick brown fox jumps over the lazy dog "


class RecordingCompiler:
    """Stands in for ``WikiCompiler``: remembers what reached the compile queue."""

    def __init__(self, *, fail_on: str | None = None) -> None:
        self.queued: list[Path] = []
        self._fail_on = fail_on

    def enqueue_file(self, file_path: Path) -> None:
        if self._fail_on is not None and file_path.name == self._fail_on:
            raise RuntimeError("queue unavailable")
        self.queued.append(file_path)


def _write(structure: WikiStructure, relative_path: str, content: str) -> Path:
    path = structure.get_raw_file_path(relative_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _names(compiler: RecordingCompiler) -> list[str]:
    return [path.name for path in compiler.queued]


@pytest.fixture
def structure(tmp_path: Path) -> WikiStructure:
    return WikiStructure(base_dir=tmp_path)


def test_nothing_reaches_the_compile_queue_until_release(structure: WikiStructure) -> None:
    compiler = RecordingCompiler()
    deferred = DeferredCompileEnqueue(compiler, structure)

    deferred.enqueue_file(_write(structure, "ima/a.md", "# A\n\nfirst"))
    deferred.enqueue_file(_write(structure, "ima/b.md", "# B\n\nsecond"))

    assert deferred.has_pending
    assert compiler.queued == []

    assert deferred.release() == 2
    assert _names(compiler) == ["a.md", "b.md"]
    assert not deferred.has_pending


def test_release_is_idempotent_and_a_file_published_twice_is_queued_once(structure: WikiStructure) -> None:
    compiler = RecordingCompiler()
    deferred = DeferredCompileEnqueue(compiler, structure)
    path = _write(structure, "ima/a.md", "# A\n\nfirst")

    deferred.enqueue_file(path)
    deferred.enqueue_file(path)

    assert deferred.release() == 1
    assert deferred.release() == 0
    assert _names(compiler) == ["a.md"]


def test_members_of_an_open_exact_group_are_held_and_the_rest_is_queued(structure: WikiStructure) -> None:
    compiler = RecordingCompiler()
    deferred = DeferredCompileEnqueue(compiler, structure)
    copies = [_write(structure, "ima/KB1/a.md", SAME_BODY), _write(structure, "ima/KB2/a-copy.md", SAME_BODY)]
    unique = _write(structure, "ima/KB1/unique.md", "# Unique\n\nNothing like the others.")
    for path in (*copies, unique):
        deferred.enqueue_file(path)
    CorpusDedupScanner(structure).scan(incremental=False)

    assert deferred.release() == 1
    assert _names(compiler) == ["unique.md"]


def test_a_normalized_duplicate_is_held_too(structure: WikiStructure) -> None:
    compiler = RecordingCompiler()
    deferred = DeferredCompileEnqueue(compiler, structure)
    deferred.enqueue_file(_write(structure, "ima/note.md", "# Title\n\nSame normalized body."))
    deferred.enqueue_file(_write(structure, "ima/page.md", "<h1>Title</h1><p>Same normalized body.</p>"))
    CorpusDedupScanner(structure).scan(incremental=False)

    assert deferred.release() == 0
    assert compiler.queued == []


def test_near_duplicates_are_not_held_because_they_never_block_compiling(structure: WikiStructure) -> None:
    compiler = RecordingCompiler()
    deferred = DeferredCompileEnqueue(compiler, structure)
    deferred.enqueue_file(_write(structure, "ima/near-a.md", f"# Near A\n\n{SHARED_NEAR * 12}end"))
    deferred.enqueue_file(_write(structure, "ima/near-b.md", f"# Near B\n\n{SHARED_NEAR * 12}ends"))
    scanner = CorpusDedupScanner(structure)
    scanner.scan(incremental=False)
    assert scanner.store.list_groups(status=GroupStatus.OPEN), "the pair must be flagged as a near group"

    assert deferred.release() == 2


def test_files_nobody_scanned_are_released(structure: WikiStructure) -> None:
    """A skipped scan (compile busy) leaves no group for the new files: they go through, as they always did."""
    compiler = RecordingCompiler()
    deferred = DeferredCompileEnqueue(compiler, structure)
    deferred.enqueue_file(_write(structure, "ima/a.md", SAME_BODY))
    deferred.enqueue_file(_write(structure, "ima/b.md", SAME_BODY))

    assert deferred.release() == 2


async def test_a_resolved_group_stops_holding_its_members(structure: WikiStructure) -> None:
    compiler = RecordingCompiler()
    deferred = DeferredCompileEnqueue(compiler, structure)
    deferred.enqueue_file(_write(structure, "ima/a.md", SAME_BODY))
    deferred.enqueue_file(_write(structure, "ima/b.md", SAME_BODY))
    scanner = CorpusDedupScanner(structure)
    scanner.scan(incremental=False)
    group = scanner.store.list_groups(status=GroupStatus.OPEN)[0]
    await CorpusDedupGovernor(structure).apply_disposition(group.group_id, DispositionAction.DISMISS, reason="")

    assert deferred.release() == 2


def test_an_unreadable_dedup_store_releases_everything_instead_of_losing_documents(
    structure: WikiStructure,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    def broken(self: CorpusDedupGovernor) -> list[object]:
        raise RuntimeError("dedup store locked")

    monkeypatch.setattr(CorpusDedupGovernor, "blocking_open_groups", broken)
    compiler = RecordingCompiler()
    deferred = DeferredCompileEnqueue(compiler, structure)
    deferred.enqueue_file(_write(structure, "ima/a.md", SAME_BODY))
    deferred.enqueue_file(_write(structure, "ima/b.md", SAME_BODY))

    with caplog.at_level(logging.WARNING):
        assert deferred.release() == 2
    assert "dedup store locked" in caplog.text


def test_one_failing_enqueue_does_not_lose_the_others(structure: WikiStructure, caplog: pytest.LogCaptureFixture) -> None:
    compiler = RecordingCompiler(fail_on="bad.md")
    deferred = DeferredCompileEnqueue(compiler, structure)
    deferred.enqueue_file(_write(structure, "ima/bad.md", "# Bad\n\nfirst"))
    deferred.enqueue_file(_write(structure, "ima/good.md", "# Good\n\nsecond"))

    with caplog.at_level(logging.WARNING):
        assert deferred.release() == 1
    assert _names(compiler) == ["good.md"]
    assert "queue unavailable" in caplog.text
