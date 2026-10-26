"""A scan reads the fingerprint cache once and stores what it recomputed in batches, not one round trip per file."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest

from myrm_agent_harness.toolkits.wiki.core.structure import WikiStructure
from myrm_agent_harness.toolkits.wiki.pipeline.corpus_dedup import CorpusDedupScanner
from myrm_agent_harness.toolkits.wiki.pipeline.corpus_dedup import scanner as scanner_module
from myrm_agent_harness.toolkits.wiki.pipeline.corpus_dedup.fingerprint_cache import FingerprintCache
from myrm_agent_harness.toolkits.wiki.pipeline.corpus_dedup.types import RawFileFingerprint


@pytest.fixture
def structure(tmp_path: Path) -> WikiStructure:
    structure = WikiStructure(tmp_path / "wiki")
    structure.ensure_structure()
    return structure


def _write_documents(structure: WikiStructure, count: int) -> None:
    for index in range(count):
        path = structure.get_raw_file_path(f"notes/doc-{index}.md")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"# Document {index}\n\nBody number {index}, about subject {index * 7919}.", encoding="utf-8")


def _record_batches(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """Sizes of the non-empty fingerprint batches the store is asked to save."""
    batches: list[int] = []
    store_batch = FingerprintCache.upsert_many

    def recording(self: FingerprintCache, fingerprints: Sequence[RawFileFingerprint]) -> None:
        if fingerprints:
            batches.append(len(fingerprints))
        store_batch(self, fingerprints)

    monkeypatch.setattr(FingerprintCache, "upsert_many", recording)
    return batches


def _record_hashed(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Raw-relative paths the scanner hashes from scratch."""
    hashed: list[str] = []
    build = scanner_module.build_fingerprint

    def recording(raw_file: Path, *, relative_path: str) -> RawFileFingerprint:
        hashed.append(relative_path)
        return build(raw_file, relative_path=relative_path)

    monkeypatch.setattr(scanner_module, "build_fingerprint", recording)
    return hashed


def test_a_full_scan_stores_the_fingerprints_in_batches(
    structure: WikiStructure, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(scanner_module, "_FINGERPRINT_BATCH", 3)
    batches = _record_batches(monkeypatch)
    _write_documents(structure, 7)
    scanner = CorpusDedupScanner(structure)

    scanner.scan(incremental=False)

    assert batches == [3, 3, 1]
    assert len(scanner.store.fingerprints.load_all()) == 7


def test_an_incremental_scan_hashes_only_the_files_that_changed(
    structure: WikiStructure, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_documents(structure, 7)
    scanner = CorpusDedupScanner(structure)
    scanner.scan(incremental=False)
    hashed = _record_hashed(monkeypatch)
    batches = _record_batches(monkeypatch)

    scanner.scan(incremental=True)
    assert hashed == [] and batches == []

    changed = structure.get_raw_file_path("notes/doc-3.md")
    changed.write_text(changed.read_text(encoding="utf-8") + "\n\nA paragraph added afterwards.", encoding="utf-8")
    scanner.scan(incremental=True)

    assert hashed == ["notes/doc-3.md"]
    assert batches == [1]


def test_a_full_scan_rehashes_every_file_even_when_all_are_cached(
    structure: WikiStructure, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_documents(structure, 5)
    scanner = CorpusDedupScanner(structure)
    scanner.scan(incremental=False)
    hashed = _record_hashed(monkeypatch)

    scanner.scan(incremental=False)

    assert len(hashed) == 5


def test_an_interrupted_scan_keeps_the_fingerprints_it_already_stored(
    structure: WikiStructure, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(scanner_module, "_FINGERPRINT_BATCH", 3)
    _write_documents(structure, 8)
    build = scanner_module.build_fingerprint
    hashed_before_failure = 0

    def failing_on_the_eighth(raw_file: Path, *, relative_path: str) -> RawFileFingerprint:
        nonlocal hashed_before_failure
        if hashed_before_failure == 7:
            raise RuntimeError("the disk went away")
        hashed_before_failure += 1
        return build(raw_file, relative_path=relative_path)

    monkeypatch.setattr(scanner_module, "build_fingerprint", failing_on_the_eighth)
    scanner = CorpusDedupScanner(structure)
    with pytest.raises(RuntimeError, match="the disk went away"):
        scanner.scan(incremental=False)

    # Seven files were hashed and two batches of three reached the store; only the unsaved seventh is lost.
    assert len(scanner.store.fingerprints.load_all()) == 6

    monkeypatch.setattr(scanner_module, "build_fingerprint", build)
    hashed = _record_hashed(monkeypatch)
    scanner.scan(incremental=True)

    assert len(hashed) == 2
    assert len(scanner.store.fingerprints.load_all()) == 8


def test_pruning_works_on_a_corpus_larger_than_sqlites_bound_variable_limit(structure: WikiStructure) -> None:
    cache = CorpusDedupScanner(structure).store.fingerprints
    paths = [f"bulk/doc-{index}.md" for index in range(40_000)]
    cache.upsert_many(
        [
            RawFileFingerprint(
                relative_path=path, exact_hash="e", normalized_hash="n", simhash=index, size_bytes=1, mtime_ns=index
            )
            for index, path in enumerate(paths)
        ]
    )

    removed = cache.prune(set(paths[:39_990]))

    assert removed == 10
    assert sorted(set(paths) - set(cache.load_all())) == sorted(paths[39_990:])


def test_pruning_an_empty_corpus_forgets_everything(structure: WikiStructure) -> None:
    _write_documents(structure, 3)
    scanner = CorpusDedupScanner(structure)
    scanner.scan(incremental=False)

    assert scanner.store.fingerprints.prune(set()) == 3
    assert scanner.store.fingerprints.load_all() == {}


def test_a_deleted_file_leaves_the_cache(structure: WikiStructure) -> None:
    _write_documents(structure, 4)
    scanner = CorpusDedupScanner(structure)
    scanner.scan(incremental=False)
    structure.get_raw_file_path("notes/doc-2.md").unlink()

    scanner.scan(incremental=True)

    assert sorted(scanner.store.fingerprints.load_all()) == ["notes/doc-0.md", "notes/doc-1.md", "notes/doc-3.md"]
