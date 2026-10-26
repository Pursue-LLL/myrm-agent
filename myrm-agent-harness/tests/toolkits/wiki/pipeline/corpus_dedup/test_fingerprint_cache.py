"""A scan reads the fingerprint cache once and stores what it recomputed in one batch after the groups, so the cache never runs ahead of them."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest

from myrm_agent_harness.toolkits.wiki.core.structure import WikiStructure
from myrm_agent_harness.toolkits.wiki.pipeline.corpus_dedup import CorpusDedupScanner, CorpusDedupStore
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


def _write_a_pair_and_a_stranger(structure: WikiStructure) -> None:
    bodies = {
        "a.md": "# Report\n\nThe very same body.",
        "b.md": "# Report\n\nThe very same body.",
        "c.md": "# Other\n\nNothing alike.",
    }
    for name, body in bodies.items():
        path = structure.get_raw_file_path(f"notes/{name}")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")


def _grouped_paths(store: CorpusDedupStore) -> list[list[str]]:
    return [sorted(member.relative_path for member in group.members) for group in store.list_groups()]


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


def test_a_scan_stores_what_it_recomputed_in_one_batch_after_the_groups(
    structure: WikiStructure, monkeypatch: pytest.MonkeyPatch
) -> None:
    order: list[str] = []
    store_groups = CorpusDedupStore.replace_scan_groups
    store_batch = FingerprintCache.upsert_many

    def groups_first(self: CorpusDedupStore, *args: object, **kwargs: object) -> None:
        order.append("groups")
        store_groups(self, *args, **kwargs)  # type: ignore[arg-type]

    def then_fingerprints(self: FingerprintCache, fingerprints: Sequence[RawFileFingerprint]) -> None:
        order.append(f"fingerprints:{len(fingerprints)}")
        store_batch(self, fingerprints)

    monkeypatch.setattr(CorpusDedupStore, "replace_scan_groups", groups_first)
    monkeypatch.setattr(FingerprintCache, "upsert_many", then_fingerprints)
    _write_documents(structure, 7)
    scanner = CorpusDedupScanner(structure)

    scanner.scan(incremental=False)

    assert order == ["groups", "fingerprints:7"]
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


def test_a_scan_interrupted_while_hashing_stores_nothing_and_the_next_one_starts_clean(
    structure: WikiStructure, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_documents(structure, 230)
    build = scanner_module.build_fingerprint
    hashed_before_failure = 0

    def failing_on_the_last(raw_file: Path, *, relative_path: str) -> RawFileFingerprint:
        nonlocal hashed_before_failure
        if hashed_before_failure == 229:
            raise RuntimeError("the disk went away")
        hashed_before_failure += 1
        return build(raw_file, relative_path=relative_path)

    monkeypatch.setattr(scanner_module, "build_fingerprint", failing_on_the_last)
    scanner = CorpusDedupScanner(structure)
    with pytest.raises(RuntimeError, match="the disk went away"):
        scanner.scan(incremental=False)

    assert scanner.store.fingerprints.load_all() == {}

    monkeypatch.setattr(scanner_module, "build_fingerprint", build)
    hashed = _record_hashed(monkeypatch)
    scanner.scan(incremental=True)

    assert len(hashed) == 230
    assert len(scanner.store.fingerprints.load_all()) == 230


def test_a_scan_that_died_before_storing_its_groups_cannot_hide_duplicates_from_the_next_one(
    structure: WikiStructure, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_a_pair_and_a_stranger(structure)

    def dying(self: CorpusDedupStore, *args: object, **kwargs: object) -> None:
        raise RuntimeError("the process died while grouping")

    with monkeypatch.context() as interrupted:
        interrupted.setattr(CorpusDedupStore, "replace_scan_groups", dying)
        with pytest.raises(RuntimeError, match="died while grouping"):
            CorpusDedupScanner(structure).scan(incremental=True)

    follow_up = CorpusDedupScanner(structure)
    follow_up.scan(incremental=True)

    assert _grouped_paths(follow_up.store) == [["notes/a.md", "notes/b.md"]]


def test_a_scan_that_died_after_storing_its_groups_is_repaired_by_the_next_one(
    structure: WikiStructure, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_a_pair_and_a_stranger(structure)

    def dying(self: FingerprintCache, fingerprints: Sequence[RawFileFingerprint]) -> None:
        raise RuntimeError("the process died while caching")

    with monkeypatch.context() as interrupted:
        interrupted.setattr(FingerprintCache, "upsert_many", dying)
        with pytest.raises(RuntimeError, match="died while caching"):
            CorpusDedupScanner(structure).scan(incremental=True)

    follow_up = CorpusDedupScanner(structure)
    assert _grouped_paths(follow_up.store) == [["notes/a.md", "notes/b.md"]]
    assert follow_up.store.fingerprints.load_all() == {}

    hashed = _record_hashed(monkeypatch)
    follow_up.scan(incremental=True)

    assert sorted(hashed) == ["notes/a.md", "notes/b.md", "notes/c.md"]
    assert _grouped_paths(follow_up.store) == [["notes/a.md", "notes/b.md"]]
    assert len(follow_up.store.fingerprints.load_all()) == 3


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
