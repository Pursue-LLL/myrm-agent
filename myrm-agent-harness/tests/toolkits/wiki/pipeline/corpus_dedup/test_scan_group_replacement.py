"""A dedup scan swaps in its groups in one step, so a failed or overlapping scan never leaves a partial set behind."""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from myrm_agent_harness.toolkits.wiki.core.structure import WikiStructure
from myrm_agent_harness.toolkits.wiki.pipeline.corpus_dedup import CorpusDedupScanner, DedupTier
from myrm_agent_harness.toolkits.wiki.pipeline.corpus_dedup import scanner as scanner_module

_SHARED = "the quick brown fox jumps over the lazy dog "


@pytest.fixture
def structure(tmp_path: Path) -> WikiStructure:
    structure = WikiStructure(tmp_path / "wiki")
    structure.ensure_structure()
    return structure


def _write(structure: WikiStructure, relative_path: str, content: str) -> None:
    path = structure.get_raw_file_path(relative_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _snapshot(scanner: CorpusDedupScanner) -> list[tuple[DedupTier, tuple[str, ...]]]:
    return sorted(
        (group.tier, tuple(member.relative_path for member in group.members)) for group in scanner.store.list_groups()
    )


def test_a_scan_that_fails_while_grouping_keeps_the_previous_groups(
    structure: WikiStructure, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write(structure, "notes/a.md", "# Same\n\nIdentical body")
    _write(structure, "archive/a-copy.md", "# Same\n\nIdentical body")
    _write(structure, "near-a.md", f"# Near A\n\n{_SHARED * 12}end")
    _write(structure, "near-b.md", f"# Near B\n\n{_SHARED * 12}ends")
    scanner = CorpusDedupScanner(structure)
    scanner.scan(incremental=False)
    before = _snapshot(scanner)
    covered_before = scanner.store.get_scan_coverage_ns()
    assert [tier for tier, _ in before] == [DedupTier.EXACT, DedupTier.NEAR]

    def broken(left: int, right: int) -> bool:
        raise RuntimeError("simhash comparison failed")

    monkeypatch.setattr(scanner_module, "is_near_duplicate", broken)
    with pytest.raises(RuntimeError, match="simhash comparison failed"):
        scanner.scan(incremental=False)

    assert _snapshot(scanner) == before
    assert scanner.store.get_scan_coverage_ns() == covered_before


def test_overlapping_scans_leave_exactly_one_complete_set_of_groups(structure: WikiStructure) -> None:
    pairs = 40
    for index in range(pairs):
        body = f"# Doc {index}\n\nBody number {index} " + "x" * index
        _write(structure, f"set{index}/a.md", body)
        _write(structure, f"set{index}/b.md", body)
    scanners = [CorpusDedupScanner(structure) for _ in range(4)]
    start_together = threading.Barrier(len(scanners), timeout=30)
    failures: list[BaseException] = []

    def scan(scanner: CorpusDedupScanner) -> None:
        try:
            start_together.wait()
            scanner.scan(incremental=False)
        except BaseException as exc:
            failures.append(exc)

    threads = [threading.Thread(target=scan, args=(scanner,)) for scanner in scanners]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert not failures
    groups = CorpusDedupScanner(structure).store.list_groups()
    assert len(groups) == pairs
    assert len({tuple(member.relative_path for member in group.members) for group in groups}) == pairs


def test_a_scan_records_the_instant_it_started_as_its_coverage(structure: WikiStructure) -> None:
    _write(structure, "a.md", "# a\n\nOnly document")
    scanner = CorpusDedupScanner(structure)
    assert scanner.store.get_scan_coverage_ns() == 0

    before = time.time_ns()
    scanner.scan(incremental=False)
    covered = scanner.store.get_scan_coverage_ns()
    assert before <= covered <= time.time_ns()

    again = time.time_ns()
    result = scanner.scan(incremental=True)
    assert result.incremental
    assert scanner.store.get_scan_coverage_ns() >= again
