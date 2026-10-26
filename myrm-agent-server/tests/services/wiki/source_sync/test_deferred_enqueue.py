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


def _scan(structure: WikiStructure) -> CorpusDedupScanner:
    scanner = CorpusDedupScanner(structure)
    scanner.scan(incremental=False)
    return scanner


def _names(compiler: RecordingCompiler) -> list[str]:
    return [path.name for path in compiler.queued]


def _held(structure: WikiStructure) -> list[str]:
    return sorted(held.relative_path for held in CorpusDedupGovernor(structure).store.holds.list_held())


@pytest.fixture
def structure(tmp_path: Path) -> WikiStructure:
    return WikiStructure(base_dir=tmp_path)


async def test_nothing_reaches_the_compile_queue_until_a_scan_has_looked_at_the_files(structure: WikiStructure) -> None:
    compiler = RecordingCompiler()
    deferred = DeferredCompileEnqueue(compiler, structure)

    deferred.enqueue_file(_write(structure, "ima/a.md", "# A\n\nfirst"))
    deferred.enqueue_file(_write(structure, "ima/b.md", "# B\n\nsecond"))

    assert deferred.needs_scan
    assert compiler.queued == []
    assert await deferred.release(scan_completed=True) == 0

    _scan(structure)

    assert not deferred.needs_scan
    assert await deferred.release(scan_completed=True) == 2
    assert _names(compiler) == ["a.md", "b.md"]
    assert _held(structure) == []


async def test_release_is_idempotent_and_a_file_published_twice_is_queued_once(structure: WikiStructure) -> None:
    compiler = RecordingCompiler()
    deferred = DeferredCompileEnqueue(compiler, structure)
    path = _write(structure, "ima/a.md", "# A\n\nfirst")

    deferred.enqueue_file(path)
    deferred.enqueue_file(path)
    _scan(structure)

    assert await deferred.release(scan_completed=True) == 1
    assert await deferred.release(scan_completed=True) == 0
    assert _names(compiler) == ["a.md"]


async def test_members_of_an_open_exact_group_are_held_and_the_rest_is_queued(structure: WikiStructure) -> None:
    compiler = RecordingCompiler()
    deferred = DeferredCompileEnqueue(compiler, structure)
    copies = [_write(structure, "ima/KB1/a.md", SAME_BODY), _write(structure, "ima/KB2/a-copy.md", SAME_BODY)]
    unique = _write(structure, "ima/KB1/unique.md", "# Unique\n\nNothing like the others.")
    for path in (*copies, unique):
        deferred.enqueue_file(path)
    _scan(structure)

    assert await deferred.release(scan_completed=True) == 1
    assert _names(compiler) == ["unique.md"]
    assert _held(structure) == ["ima/KB1/a.md", "ima/KB2/a-copy.md"]


async def test_a_normalized_duplicate_is_held_too(structure: WikiStructure) -> None:
    compiler = RecordingCompiler()
    deferred = DeferredCompileEnqueue(compiler, structure)
    deferred.enqueue_file(_write(structure, "ima/note.md", "# Title\n\nSame normalized body."))
    deferred.enqueue_file(_write(structure, "ima/page.md", "<h1>Title</h1><p>Same normalized body.</p>"))
    _scan(structure)

    assert await deferred.release(scan_completed=True) == 0
    assert compiler.queued == []


async def test_near_duplicates_are_not_held_because_they_never_block_compiling(structure: WikiStructure) -> None:
    compiler = RecordingCompiler()
    deferred = DeferredCompileEnqueue(compiler, structure)
    deferred.enqueue_file(_write(structure, "ima/near-a.md", f"# Near A\n\n{SHARED_NEAR * 12}end"))
    deferred.enqueue_file(_write(structure, "ima/near-b.md", f"# Near B\n\n{SHARED_NEAR * 12}ends"))
    scanner = _scan(structure)
    assert scanner.store.list_groups(status=GroupStatus.OPEN), "the pair must be flagged as a near group"

    assert await deferred.release(scan_completed=True) == 2


async def test_a_dismissed_pair_is_no_longer_held(structure: WikiStructure) -> None:
    compiler = RecordingCompiler()
    deferred = DeferredCompileEnqueue(compiler, structure)
    deferred.enqueue_file(_write(structure, "ima/a.md", SAME_BODY))
    deferred.enqueue_file(_write(structure, "ima/b.md", SAME_BODY))
    (group,) = _scan(structure).store.list_groups(status=GroupStatus.OPEN)
    await CorpusDedupGovernor(structure).apply_disposition(group.group_id, DispositionAction.DISMISS, reason="")

    assert await deferred.release(scan_completed=True) == 2


async def test_without_a_completed_scan_this_runs_files_are_released_even_when_groups_are_stored(
    structure: WikiStructure,
) -> None:
    """Stored groups describe the last scan that finished, not the files published since: do not trust them."""
    _write(structure, "ima/old-a.md", SAME_BODY)
    _write(structure, "ima/old-b.md", SAME_BODY)
    _scan(structure)
    compiler = RecordingCompiler()
    deferred = DeferredCompileEnqueue(compiler, structure)
    deferred.enqueue_file(_write(structure, "ima/a.md", SAME_BODY))
    deferred.enqueue_file(_write(structure, "ima/b.md", SAME_BODY))

    assert await deferred.release(scan_completed=False) == 2
    assert _names(compiler) == ["a.md", "b.md"]
    assert _held(structure) == []


async def test_files_left_by_a_run_that_died_are_released_after_the_next_scan(structure: WikiStructure) -> None:
    crashed = DeferredCompileEnqueue(RecordingCompiler(), structure)
    crashed.enqueue_file(_write(structure, "ima/a.md", "# A\n\nfirst"))
    crashed.enqueue_file(_write(structure, "ima/b.md", "# B\n\nsecond"))

    compiler = RecordingCompiler()
    next_run = DeferredCompileEnqueue(compiler, structure)
    assert next_run.needs_scan, "files held by a dead run still owe a scan"
    _scan(structure)

    assert await next_run.release(scan_completed=True) == 2
    assert _names(compiler) == ["a.md", "b.md"]


async def test_a_held_duplicate_is_compiled_once_the_user_resolves_its_group(structure: WikiStructure) -> None:
    compiler = RecordingCompiler()
    deferred = DeferredCompileEnqueue(compiler, structure)
    deferred.enqueue_file(_write(structure, "ima/KB1/a.md", SAME_BODY))
    deferred.enqueue_file(_write(structure, "ima/KB2/a-copy.md", SAME_BODY))
    (group,) = _scan(structure).store.list_groups(status=GroupStatus.OPEN)
    assert await deferred.release(scan_completed=True) == 0

    # Duplicate Review in a later session: nothing but the user's decision is needed for the survivor to compile.
    await CorpusDedupGovernor(structure).apply_disposition(
        group.group_id, DispositionAction.TRASH, reason="copy", compiler=compiler
    )

    assert compiler.queued == [structure.get_raw_file_path(group.recommended_keep_path)]
    assert _held(structure) == []


async def test_an_unreadable_dedup_store_queues_this_runs_files_directly(
    structure: WikiStructure,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    async def broken(self: CorpusDedupGovernor, enqueuer: object) -> int:
        raise RuntimeError("dedup store locked")

    monkeypatch.setattr(CorpusDedupGovernor, "release_held", broken)
    compiler = RecordingCompiler()
    deferred = DeferredCompileEnqueue(compiler, structure)
    deferred.enqueue_file(_write(structure, "ima/a.md", SAME_BODY))
    deferred.enqueue_file(_write(structure, "ima/b.md", SAME_BODY))

    with caplog.at_level(logging.WARNING):
        assert await deferred.release(scan_completed=True) == 2
    assert "dedup store locked" in caplog.text


async def test_a_hold_that_cannot_be_stored_queues_the_file_at_once(
    structure: WikiStructure,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    def broken(self: CorpusDedupGovernor, relative_paths: object) -> None:
        raise RuntimeError("disk full")

    monkeypatch.setattr(CorpusDedupGovernor, "hold_for_compile", broken)
    compiler = RecordingCompiler()
    deferred = DeferredCompileEnqueue(compiler, structure)

    with caplog.at_level(logging.WARNING):
        deferred.enqueue_file(_write(structure, "ima/a.md", "# A\n\nfirst"))

    assert _names(compiler) == ["a.md"]
    assert "disk full" in caplog.text
    assert await deferred.release(scan_completed=False) == 0


async def test_a_file_outside_the_raw_folder_is_queued_at_once(structure: WikiStructure, tmp_path: Path) -> None:
    compiler = RecordingCompiler()
    deferred = DeferredCompileEnqueue(compiler, structure)
    elsewhere = tmp_path / "elsewhere.md"
    elsewhere.write_text("# Elsewhere\n\nnot a raw file", encoding="utf-8")

    deferred.enqueue_file(elsewhere)

    assert compiler.queued == [elsewhere]
    assert not deferred.needs_scan


async def test_one_failing_enqueue_does_not_lose_the_others(structure: WikiStructure, caplog: pytest.LogCaptureFixture) -> None:
    compiler = RecordingCompiler(fail_on="bad.md")
    deferred = DeferredCompileEnqueue(compiler, structure)
    deferred.enqueue_file(_write(structure, "ima/bad.md", "# Bad\n\nfirst"))
    deferred.enqueue_file(_write(structure, "ima/good.md", "# Good\n\nsecond"))
    _scan(structure)

    with caplog.at_level(logging.WARNING):
        assert await deferred.release(scan_completed=True) == 1
    assert _names(compiler) == ["good.md"]
    assert "queue unavailable" in caplog.text
    assert _held(structure) == ["ima/bad.md"]

    healthy = RecordingCompiler()
    assert await DeferredCompileEnqueue(healthy, structure).release(scan_completed=True) == 1
    assert _names(healthy) == ["bad.md"]


async def test_a_run_with_nothing_to_scan_still_retries_what_an_earlier_enqueue_failure_left_held(
    structure: WikiStructure,
) -> None:
    failing = DeferredCompileEnqueue(RecordingCompiler(fail_on="bad.md"), structure)
    failing.enqueue_file(_write(structure, "ima/bad.md", "# Bad\n\nfirst"))
    _scan(structure)
    assert await failing.release(scan_completed=True) == 0
    assert _held(structure) == ["ima/bad.md"]

    healthy = RecordingCompiler()
    next_run = DeferredCompileEnqueue(healthy, structure)
    assert not next_run.needs_scan, "the file is covered by a finished scan, nothing is owed"

    assert await next_run.release(scan_completed=False) == 1
    assert _names(healthy) == ["bad.md"]
    assert _held(structure) == []


async def test_a_run_with_nothing_to_scan_does_not_release_the_members_of_an_open_group(structure: WikiStructure) -> None:
    held = DeferredCompileEnqueue(RecordingCompiler(), structure)
    held.enqueue_file(_write(structure, "ima/a.md", SAME_BODY))
    held.enqueue_file(_write(structure, "ima/b.md", SAME_BODY))
    _scan(structure)
    assert await held.release(scan_completed=True) == 0

    compiler = RecordingCompiler()
    assert await DeferredCompileEnqueue(compiler, structure).release(scan_completed=False) == 0
    assert compiler.queued == []
    assert _held(structure) == ["ima/a.md", "ima/b.md"]
