"""The disposition ledger keeps the user's excluded, trashed and dismissed decisions, and the store builds on them."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from myrm_agent_harness.toolkits.wiki.core.structure import WikiStructure
from myrm_agent_harness.toolkits.wiki.pipeline.corpus_dedup import CorpusDedupStore, GroupStatus

# A vault database that holds decisions, groups and scan metadata but has neither the fingerprint cache nor the
# compile hold tables.
_SCHEMA_WITHOUT_CACHE_AND_HOLDS = """
CREATE TABLE excluded_paths (relative_path TEXT PRIMARY KEY, reason TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE trashed_paths (
    relative_path TEXT PRIMARY KEY, trash_relpath TEXT NOT NULL, content_hash TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE TABLE dismissed_pairs (
    path_a TEXT NOT NULL, path_b TEXT NOT NULL, created_at TEXT NOT NULL, PRIMARY KEY (path_a, path_b)
);
CREATE TABLE duplicate_groups (
    id INTEGER PRIMARY KEY AUTOINCREMENT, tier TEXT NOT NULL, fingerprint TEXT NOT NULL,
    recommended_keep_path TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'open', created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE group_members (
    group_id INTEGER NOT NULL, relative_path TEXT NOT NULL, size_bytes INTEGER NOT NULL, mtime_ns INTEGER NOT NULL,
    PRIMARY KEY (group_id, relative_path), FOREIGN KEY (group_id) REFERENCES duplicate_groups(id) ON DELETE CASCADE
);
CREATE TABLE dedup_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""


@pytest.fixture
def structure(tmp_path: Path) -> WikiStructure:
    structure = WikiStructure(tmp_path / "wiki")
    structure.ensure_structure()
    return structure


@pytest.fixture
def store(structure: WikiStructure) -> CorpusDedupStore:
    return CorpusDedupStore(structure)


def test_excluded_paths_are_keyed_without_the_raw_prefix_and_listed_newest_first(store: CorpusDedupStore) -> None:
    ledger = store.dispositions
    ledger.add_excluded_path("b.md", reason="duplicate")
    ledger.add_excluded_path("raw/a.md", reason="manual")

    assert ledger.get_excluded_paths() == {"a.md", "b.md"}
    entry = ledger.get_excluded_entry("a.md")
    assert entry is not None and entry.reason == "manual"
    assert [item.relative_path for item in ledger.list_excluded_entries()] == ["a.md", "b.md"]

    assert ledger.remove_excluded_path("raw/a.md") is True
    assert ledger.remove_excluded_path("a.md") is False
    assert ledger.get_excluded_entry("a.md") is None
    assert ledger.get_excluded_paths() == {"b.md"}


def test_excluding_a_path_again_replaces_its_reason(store: CorpusDedupStore) -> None:
    store.dispositions.add_excluded_path("a.md", reason="first")
    store.dispositions.add_excluded_path("a.md", reason="second")

    entries = store.dispositions.list_excluded_entries()

    assert [(item.relative_path, item.reason) for item in entries] == [("a.md", "second")]


def test_a_trashed_path_remembers_where_its_file_went(store: CorpusDedupStore) -> None:
    ledger = store.dispositions
    ledger.add_trashed_path("raw/gone.md", trash_relpath=".corpus_trash/gone.md", content_hash="abc123")

    entry = ledger.get_trashed_entry("gone.md")

    assert entry is not None
    assert (entry.relative_path, entry.trash_relpath, entry.content_hash) == (
        "gone.md",
        ".corpus_trash/gone.md",
        "abc123",
    )
    assert ledger.get_trashed_paths() == {"gone.md"}
    assert [item.relative_path for item in ledger.list_trashed_entries()] == ["gone.md"]

    assert ledger.remove_trashed_path("gone.md") is True
    assert ledger.remove_trashed_path("gone.md") is False
    assert ledger.get_trashed_entry("gone.md") is None


def test_a_dismissed_pair_is_the_same_pair_in_either_order(store: CorpusDedupStore) -> None:
    ledger = store.dispositions

    ledger.add_dismissed_pair("b.md", "a.md")
    ledger.add_dismissed_pair("a.md", "b.md")

    assert ledger.is_pair_dismissed("a.md", "b.md") is True
    assert ledger.is_pair_dismissed("b.md", "a.md") is True
    assert ledger.is_pair_dismissed("a.md", "c.md") is False


def test_the_hygiene_snapshot_lists_what_was_trashed_and_excluded(store: CorpusDedupStore) -> None:
    store.dispositions.add_excluded_path("kept-out.md", reason="manual")
    store.dispositions.add_trashed_path("trashed.md", trash_relpath=".corpus_trash/trashed.md", content_hash="")

    snapshot = store.dispositions.build_vault_hygiene_snapshot()

    assert [item.relative_path for item in snapshot.excluded] == ["kept-out.md"]
    assert [item.relative_path for item in snapshot.trashed] == ["trashed.md"]


def test_stats_count_every_excluded_and_trashed_path(store: CorpusDedupStore) -> None:
    store.dispositions.add_excluded_path("one.md", reason="manual")
    store.dispositions.add_excluded_path("two.md", reason="manual")
    store.dispositions.add_trashed_path("three.md", trash_relpath=".corpus_trash/three.md", content_hash="")

    stats = store.build_stats(eligible_raw_count=5)

    assert (stats.excluded_raw_count, stats.trashed_raw_count, stats.eligible_raw_count) == (2, 1, 5)
    assert (stats.duplicate_groups_pending, stats.compile_jobs_prevented) == (0, 0)


def test_decisions_survive_reopening_the_store(structure: WikiStructure) -> None:
    CorpusDedupStore(structure).dispositions.add_excluded_path("a.md", reason="manual")

    reopened = CorpusDedupStore(structure)

    assert reopened.dispositions.get_excluded_paths() == {"a.md"}


def test_a_vault_database_without_the_cache_and_hold_tables_opens_with_its_data_intact(
    structure: WikiStructure,
) -> None:
    db_path = structure.base_dir / ".raw_dedup.db"
    conn = sqlite3.connect(db_path)
    with conn:
        conn.executescript(_SCHEMA_WITHOUT_CACHE_AND_HOLDS)
        conn.execute("INSERT INTO excluded_paths VALUES ('decided.md', 'manual', '2026-01-01T00:00:00+00:00')")
        conn.execute(
            "INSERT INTO duplicate_groups (id, tier, fingerprint, recommended_keep_path, status, created_at, updated_at)"
            " VALUES (7, 'exact', 'f', 'x.md', 'open', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')"
        )
        conn.executemany("INSERT INTO group_members VALUES (7, ?, 10, 1)", [("x.md",), ("y.md",)])
        conn.execute("INSERT INTO dedup_meta VALUES ('last_scan_at', '2026-01-01T00:00:00+00:00')")
    conn.close()

    store = CorpusDedupStore(structure)

    assert store.dispositions.get_excluded_paths() == {"decided.md"}
    groups = store.list_groups(status=GroupStatus.OPEN)
    assert [(group.group_id, sorted(member.relative_path for member in group.members)) for group in groups] == [
        (7, ["x.md", "y.md"])
    ]
    assert store.get_last_scan_at() == "2026-01-01T00:00:00+00:00"
    # No scan has stored a coverage instant yet, so anything held now still needs one.
    assert store.get_scan_coverage_ns() == 0
    store.holds.hold(["new.md"], held_at_ns=1)
    assert store.holds.any_held_after(store.get_scan_coverage_ns()) is True
    assert store.fingerprints.load_all() == {}
