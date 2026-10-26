"""Held files wait for a scan that began after they were written, and leave once the duplicate review clears them."""

from __future__ import annotations

import hashlib
import json
import logging
import time
from pathlib import Path

import pytest

from myrm_agent_harness.toolkits.wiki.core.claims_contract import LAST_COMPILE_RAW_HASHES_KEY, raw_relative_storage_key
from myrm_agent_harness.toolkits.wiki.core.structure import WikiStructure
from myrm_agent_harness.toolkits.wiki.pipeline.corpus_dedup import (
    CorpusDedupGovernor,
    CorpusDedupScanner,
    DispositionAction,
    GroupStatus,
)
from myrm_agent_harness.toolkits.wiki.pipeline.queue import WikiIngestionQueue

_SAME_BODY = "# Report\n\nThe very same body, imported twice."


class RecordingEnqueuer:
    """Stands in for ``WikiCompiler``: remembers which files reached the compile queue."""

    def __init__(self, *, fail_on: str | None = None) -> None:
        self.queued: list[Path] = []
        self._fail_on = fail_on

    def enqueue_file(self, file_path: Path) -> None:
        if self._fail_on is not None and file_path.name == self._fail_on:
            raise RuntimeError("queue unavailable")
        self.queued.append(file_path)

    @property
    def names(self) -> list[str]:
        return [path.name for path in self.queued]


@pytest.fixture
def structure(tmp_path: Path) -> WikiStructure:
    structure = WikiStructure(tmp_path / "wiki")
    structure.ensure_structure()
    return structure


@pytest.fixture
def governor(structure: WikiStructure) -> CorpusDedupGovernor:
    return CorpusDedupGovernor(structure)


def _write(structure: WikiStructure, relative_path: str, content: str) -> Path:
    path = structure.get_raw_file_path(relative_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _scan(structure: WikiStructure) -> CorpusDedupScanner:
    scanner = CorpusDedupScanner(structure)
    scanner.scan(incremental=False)
    return scanner


def _held_paths(governor: CorpusDedupGovernor) -> list[str]:
    return sorted(held.relative_path for held in governor.store.holds.list_held())


async def test_a_held_file_waits_until_a_scan_has_looked_at_it(
    structure: WikiStructure, governor: CorpusDedupGovernor
) -> None:
    _write(structure, "ima/a.md", "# A\n\nfirst")
    governor.hold_for_compile(["ima/a.md"])
    enqueuer = RecordingEnqueuer()

    assert governor.has_unscanned_holds()
    assert await governor.release_held(enqueuer) == 0
    assert _held_paths(governor) == ["ima/a.md"]

    _scan(structure)

    assert not governor.has_unscanned_holds()
    assert await governor.release_held(enqueuer) == 1
    assert enqueuer.queued == [structure.get_raw_file_path("ima/a.md")]
    assert _held_paths(governor) == []


async def test_a_file_held_after_a_scan_began_is_not_covered_by_it(
    structure: WikiStructure, governor: CorpusDedupGovernor
) -> None:
    _write(structure, "early.md", "# Early\n\nwritten before the scan")
    _write(structure, "late.md", "# Late\n\nwritten while the scan ran")
    _scan(structure)
    covered = governor.store.get_scan_coverage_ns()
    governor.store.holds.hold(["early.md"], held_at_ns=covered)
    governor.store.holds.hold(["late.md"], held_at_ns=covered + 1)
    enqueuer = RecordingEnqueuer()

    assert governor.has_unscanned_holds()
    assert await governor.release_held(enqueuer) == 1
    assert enqueuer.names == ["early.md"]
    assert _held_paths(governor) == ["late.md"]


async def test_holding_a_file_again_after_a_scan_makes_it_wait_for_the_next_scan(
    structure: WikiStructure, governor: CorpusDedupGovernor
) -> None:
    _write(structure, "a.md", "# A\n\nfirst version")
    governor.hold_for_compile(["a.md"])
    _scan(structure)
    time.sleep(0.002)
    _write(structure, "a.md", "# A\n\nsecond version")
    governor.hold_for_compile(["a.md"])
    enqueuer = RecordingEnqueuer()

    assert await governor.release_held(enqueuer) == 0
    _scan(structure)
    assert await governor.release_held(enqueuer) == 1


async def test_holds_survive_a_restart(structure: WikiStructure, governor: CorpusDedupGovernor) -> None:
    _write(structure, "ima/a.md", "# A\n\nfirst")
    governor.hold_for_compile(["ima/a.md"])
    _scan(structure)
    enqueuer = RecordingEnqueuer()

    assert await CorpusDedupGovernor(structure).release_held(enqueuer) == 1
    assert enqueuer.names == ["a.md"]


async def test_members_of_an_open_group_stay_held_until_the_user_decides(
    structure: WikiStructure, governor: CorpusDedupGovernor
) -> None:
    _write(structure, "kept.md", _SAME_BODY)
    _write(structure, "archive/old.md", _SAME_BODY)
    _write(structure, "unique.md", "# Unique\n\nNothing like the others.")
    governor.hold_for_compile(["kept.md", "archive/old.md", "unique.md"])
    _scan(structure)
    enqueuer = RecordingEnqueuer()

    assert await governor.release_held(enqueuer) == 1
    assert enqueuer.names == ["unique.md"]
    assert _held_paths(governor) == ["archive/old.md", "kept.md"]


async def test_trashing_the_copy_compiles_the_held_survivor(
    structure: WikiStructure, governor: CorpusDedupGovernor
) -> None:
    _write(structure, "kept.md", _SAME_BODY)
    _write(structure, "archive/old.md", _SAME_BODY)
    governor.hold_for_compile(["kept.md", "archive/old.md"])
    scanner = _scan(structure)
    (group,) = scanner.store.list_groups(status=GroupStatus.OPEN)
    assert group.recommended_keep_path == "kept.md"
    enqueuer = RecordingEnqueuer()

    await governor.apply_disposition(group.group_id, DispositionAction.TRASH, reason="copy", compiler=enqueuer)  # type: ignore[arg-type]

    assert enqueuer.queued == [structure.get_raw_file_path("kept.md")]
    assert _held_paths(governor) == []


async def test_a_held_copy_that_is_trashed_is_never_queued(
    structure: WikiStructure, governor: CorpusDedupGovernor
) -> None:
    _write(structure, "kept.md", _SAME_BODY)
    _write(structure, "archive/old.md", _SAME_BODY)
    governor.hold_for_compile(["archive/old.md"])
    scanner = _scan(structure)
    (group,) = scanner.store.list_groups(status=GroupStatus.OPEN)
    enqueuer = RecordingEnqueuer()

    await governor.apply_disposition(group.group_id, DispositionAction.TRASH, reason="copy", compiler=enqueuer)  # type: ignore[arg-type]

    assert enqueuer.queued == []
    assert _held_paths(governor) == []


@pytest.mark.parametrize("action", [DispositionAction.DISMISS, DispositionAction.DEFER])
async def test_dismissing_or_deferring_a_group_releases_its_held_files(
    structure: WikiStructure, governor: CorpusDedupGovernor, action: DispositionAction
) -> None:
    _write(structure, "a.md", _SAME_BODY)
    _write(structure, "b.md", _SAME_BODY)
    governor.hold_for_compile(["a.md", "b.md"])
    scanner = _scan(structure)
    (group,) = scanner.store.list_groups(status=GroupStatus.OPEN)
    enqueuer = RecordingEnqueuer()

    await governor.apply_disposition(group.group_id, action, reason="", compiler=enqueuer)  # type: ignore[arg-type]

    assert sorted(enqueuer.names) == ["a.md", "b.md"]
    assert _held_paths(governor) == []


async def test_a_disposition_without_a_compiler_leaves_the_holds_alone(
    structure: WikiStructure, governor: CorpusDedupGovernor
) -> None:
    _write(structure, "a.md", _SAME_BODY)
    _write(structure, "b.md", _SAME_BODY)
    governor.hold_for_compile(["a.md", "b.md"])
    scanner = _scan(structure)
    (group,) = scanner.store.list_groups(status=GroupStatus.OPEN)

    await governor.apply_disposition(group.group_id, DispositionAction.DISMISS, reason="")

    assert _held_paths(governor) == ["a.md", "b.md"]
    enqueuer = RecordingEnqueuer()
    assert await governor.release_held(enqueuer) == 2


async def test_near_duplicates_never_block_a_release(structure: WikiStructure, governor: CorpusDedupGovernor) -> None:
    shared = "the quick brown fox jumps over the lazy dog "
    _write(structure, "near-a.md", f"# Near A\n\n{shared * 12}end")
    _write(structure, "near-b.md", f"# Near B\n\n{shared * 12}ends")
    governor.hold_for_compile(["near-a.md", "near-b.md"])
    scanner = _scan(structure)
    assert scanner.store.list_groups(status=GroupStatus.OPEN), "the pair must be flagged as a near group"
    enqueuer = RecordingEnqueuer()

    assert await governor.release_held(enqueuer) == 2


async def test_excluded_trashed_and_vanished_files_are_settled_without_queueing(
    structure: WikiStructure, governor: CorpusDedupGovernor
) -> None:
    _write(structure, "excluded.md", "# Excluded\n\nbody one")
    _write(structure, "trashed.md", "# Trashed\n\nbody two")
    _write(structure, "gone.md", "# Gone\n\nbody three")
    governor.hold_for_compile(["excluded.md", "trashed.md", "gone.md"])
    _scan(structure)
    governor.store.dispositions.add_excluded_path("excluded.md", reason="manual")
    governor.store.dispositions.add_trashed_path("trashed.md", trash_relpath=".corpus_trash/x", content_hash="")
    structure.get_raw_file_path("gone.md").unlink()
    enqueuer = RecordingEnqueuer()

    assert await governor.release_held(enqueuer) == 0
    assert enqueuer.queued == []
    assert _held_paths(governor) == []


async def test_a_file_whose_content_was_compiled_meanwhile_is_not_queued_again(
    structure: WikiStructure, governor: CorpusDedupGovernor
) -> None:
    raw = _write(structure, "a.md", "# A\n\nalready compiled")
    known = {raw_relative_storage_key(structure, raw): hashlib.sha256(raw.read_bytes()).hexdigest()}
    structure.get_wiki_metadata_path().write_text(json.dumps({LAST_COMPILE_RAW_HASHES_KEY: known}))
    governor.hold_for_compile(["a.md"])
    _scan(structure)
    enqueuer = RecordingEnqueuer()

    assert await governor.release_held(enqueuer) == 0
    assert _held_paths(governor) == []


async def test_a_file_being_compiled_right_now_is_not_queued_again(
    structure: WikiStructure, governor: CorpusDedupGovernor
) -> None:
    raw = _write(structure, "a.md", "# A\n\nbeing compiled")
    queue = WikiIngestionQueue(structure)
    queue.add_item(raw)
    claimed = queue.get_pending_items()[0]
    queue.mark_processing(claimed["id"])
    governor.hold_for_compile(["a.md"])
    _scan(structure)
    enqueuer = RecordingEnqueuer()

    assert await governor.release_held(enqueuer) == 0
    assert _held_paths(governor) == []


async def test_releasing_twice_queues_a_file_once(structure: WikiStructure, governor: CorpusDedupGovernor) -> None:
    _write(structure, "a.md", "# A\n\nfirst")
    governor.hold_for_compile(["a.md", "a.md"])
    _scan(structure)
    enqueuer = RecordingEnqueuer()

    assert await governor.release_held(enqueuer) == 1
    assert await governor.release_held(enqueuer) == 0
    assert enqueuer.names == ["a.md"]


async def test_a_failing_enqueue_keeps_only_that_file_held(
    structure: WikiStructure, governor: CorpusDedupGovernor, caplog: pytest.LogCaptureFixture
) -> None:
    _write(structure, "bad.md", "# Bad\n\nfirst")
    _write(structure, "good.md", "# Good\n\nsecond")
    governor.hold_for_compile(["bad.md", "good.md"])
    _scan(structure)

    with caplog.at_level(logging.WARNING):
        assert await governor.release_held(RecordingEnqueuer(fail_on="bad.md")) == 1
    assert "queue unavailable" in caplog.text
    assert _held_paths(governor) == ["bad.md"]

    healthy = RecordingEnqueuer()
    assert await governor.release_held(healthy) == 1
    assert healthy.names == ["bad.md"]


async def test_a_file_held_again_while_it_was_being_released_stays_held(
    structure: WikiStructure, governor: CorpusDedupGovernor
) -> None:
    _write(structure, "a.md", "# A\n\nfirst version")
    governor.hold_for_compile(["a.md"])
    _scan(structure)

    class RewritingEnqueuer(RecordingEnqueuer):
        def enqueue_file(self, file_path: Path) -> None:
            super().enqueue_file(file_path)
            time.sleep(0.002)
            governor.hold_for_compile(["a.md"])

    assert await governor.release_held(RewritingEnqueuer()) == 1
    assert _held_paths(governor) == ["a.md"]


async def test_an_unguarded_release_queues_only_the_given_files_whatever_the_groups_say(
    structure: WikiStructure, governor: CorpusDedupGovernor
) -> None:
    _write(structure, "a.md", _SAME_BODY)
    _write(structure, "b.md", _SAME_BODY)
    _write(structure, "other.md", "# Other\n\nunrelated")
    governor.hold_for_compile(["a.md", "b.md", "other.md"])
    _scan(structure)
    enqueuer = RecordingEnqueuer()

    assert await governor.release_unguarded(enqueuer, ["a.md", "b.md"]) == 2
    assert sorted(enqueuer.names) == ["a.md", "b.md"]
    assert _held_paths(governor) == ["other.md"]
