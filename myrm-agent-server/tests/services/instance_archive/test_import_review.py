"""The review shown before a restore: when the backup was made, what it declares and lacks, and how it compares with the running app."""

from __future__ import annotations

import json
import sqlite3
import zipfile
from dataclasses import replace
from pathlib import Path

import pytest

from app.services.instance_archive import export_service, stage_db
from app.services.instance_archive.import_service import (
    _MAX_REENTRY_ITEMS,
    _MAX_REENTRY_LENGTH,
    _MAX_UNREADABLE,
    _backup_time,
    _bounded_count,
    _bounded_reentry,
)
from app.services.instance_archive.policy import StateScan
from tests.services.instance_archive.archive_flow import export_archive, stage_archive


def test_review_describes_the_backup_next_to_the_running_instance(source_state: Path, target_state: Path, tmp_path: Path) -> None:
    archive = export_archive(source_state, tmp_path / "out.zip")
    with zipfile.ZipFile(archive) as zf:
        made_at = json.loads(zf.read("manifest.json"))["created_at"]

    report, *_ = stage_archive(target_state, archive)

    assert report.created_at == made_at  # when the backup was made, not when it was staged
    assert report.counts == {"chats": 1, "messages": 1, "agents": 1, "cron_jobs": 1, "skills": 1, "wiki_pages": 1}
    assert report.current_counts == {"chats": 1, "messages": 0, "agents": 0, "cron_jobs": 0}
    assert report.unreadable_count == 0  # a complete backup lacks nothing


def test_review_tells_how_many_items_the_backup_lacks(
    source_state: Path, target_state: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A restore swaps whole top-level trees, so what the export could not read is gone afterwards: the review says so."""
    real_scan = export_service.scan_state_dir

    def scan_with_unreadable(state_dir: Path) -> StateScan:
        return replace(real_scan(state_dir), unreadable=["wiki/locked.md", "wiki/private"])

    monkeypatch.setattr(export_service, "scan_state_dir", scan_with_unreadable)

    report, *_ = stage_archive(target_state, export_archive(source_state, tmp_path / "out.zip"))

    assert report.unreadable_count == 2
    assert report.to_dict()["unreadable_count"] == 2


def _add_unlisted_chats(db: Path, *, trashed: int, incognito: int) -> None:
    """Give the fixture's chats table the columns the app lists by, plus chats the list hides."""
    conn = sqlite3.connect(db)
    try:
        conn.execute("ALTER TABLE chats ADD COLUMN deleted_at TEXT")
        conn.execute("ALTER TABLE chats ADD COLUMN is_incognito INTEGER NOT NULL DEFAULT 0")
        conn.executemany("INSERT INTO chats (id, deleted_at) VALUES (?, '2026-01-01')", [(f"trash{i}",) for i in range(trashed)])
        conn.executemany("INSERT INTO chats (id, is_incognito) VALUES (?, 1)", [(f"incognito{i}",) for i in range(incognito)])
        conn.commit()
    finally:
        conn.close()


def test_review_counts_only_the_chats_the_app_lists(source_state: Path, target_state: Path, tmp_path: Path) -> None:
    _add_unlisted_chats(source_state / "data.db", trashed=2, incognito=1)
    _add_unlisted_chats(target_state / "data.db", trashed=3, incognito=2)

    report, *_ = stage_archive(target_state, export_archive(source_state, tmp_path / "out.zip"))

    assert report.counts["chats"] == 1  # the one chat in the sidebar, not the three rows behind it
    assert report.current_counts["chats"] == 1


def test_review_has_no_comparison_without_a_running_database(source_state: Path, tmp_path: Path) -> None:
    fresh = tmp_path / "fresh"
    fresh.mkdir()

    report, *_ = stage_archive(fresh, export_archive(source_state, tmp_path / "out.zip"))

    assert report.current_counts == {}
    assert report.counts["chats"] == 1


def test_review_survives_an_unreadable_running_database(
    source_state: Path, target_state: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    count_rows = stage_db.count_rows

    def locked_live(conn: sqlite3.Connection, table: str, schema: str = "main", where: str = "") -> int:
        if schema == "live":
            raise sqlite3.OperationalError("database is locked")
        return count_rows(conn, table, schema, where)

    monkeypatch.setattr(stage_db, "count_rows", locked_live)

    report, *_ = stage_archive(target_state, export_archive(source_state, tmp_path / "out.zip"))

    assert report.current_counts == {}
    assert report.counts["chats"] == 1


@pytest.mark.parametrize("raw", ["", "yesterday", "9" * 10_000, "2026-13-45T99:00:00Z"])
def test_a_manifest_timestamp_that_is_not_one_is_dropped(raw: str) -> None:
    assert _backup_time(raw) == ""


def test_a_manifest_timestamp_is_reported_in_canonical_form() -> None:
    assert _backup_time("2026-09-13T12:00:00+00:00") == "2026-09-13T12:00:00+00:00"


def test_reentry_merges_what_the_archive_declares_with_what_staging_found() -> None:
    declared = ["table:agent_secrets", "config:providers", "path:matrix"]

    assert _bounded_reentry(declared, ("config:providers", "config:mcpServers")) == (
        "config:mcpServers",
        "config:providers",
        "path:matrix",
        "table:agent_secrets",
    )


@pytest.mark.parametrize("declared", [None, "config:providers", {"config:providers": 1}, 7])
def test_reentry_declared_as_anything_but_a_list_is_ignored(declared: object) -> None:
    assert _bounded_reentry(declared, ("config:mcpServers",)) == ("config:mcpServers",)


def test_reentry_drops_entries_that_are_not_well_formed() -> None:
    declared = ["config:providers", 5, None, ["config:x"], "providers", "shell:rm -rf", "path:" + "x" * _MAX_REENTRY_LENGTH]

    assert _bounded_reentry(declared, ()) == ("config:providers",)


def test_reentry_is_capped_so_a_hostile_manifest_cannot_inflate_the_report() -> None:
    declared = [f"path:vault-{i:06d}" for i in range(_MAX_REENTRY_ITEMS * 50)]

    kept = _bounded_reentry(declared, ())

    assert len(kept) == _MAX_REENTRY_ITEMS
    assert kept == tuple(sorted(declared)[:_MAX_REENTRY_ITEMS])  # the same set on every review


@pytest.mark.parametrize(
    ("declared", "expected"),
    [
        (0, 0),
        (3, 3),
        (_MAX_UNREADABLE, _MAX_UNREADABLE),
        (_MAX_UNREADABLE * 10, _MAX_UNREADABLE),
        (-1, 0),
        (True, 0),
        (2.0, 0),
        ("3", 0),
        ([3], 0),
        (None, 0),
    ],
)
def test_the_declared_unreadable_count_is_only_trusted_as_a_plain_non_negative_integer(declared: object, expected: int) -> None:
    assert _bounded_count(declared) == expected
