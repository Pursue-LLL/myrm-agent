"""Path classification: include-by-default, explicit exclusions, hostile-entry gate."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.services.instance_archive import policy
from app.services.instance_archive.policy import (
    PathCategory,
    classify_path,
    is_importable_entry,
    scan_state_dir,
)
from tests.services.instance_archive.conftest import PERMISSIONS_ENFORCED


@pytest.mark.parametrize(
    ("parts", "category"),
    [
        (("data.db",), PathCategory.DATA),
        (("data.db-wal",), PathCategory.RUNTIME),
        (("brand_new_store.db",), PathCategory.DATA),  # unknown stays in: never silently lost
        ((".encryption_key",), PathCategory.MACHINE_KEY),
        (("vault.key",), PathCategory.MACHINE_KEY),
        (("session_vault", "x"), PathCategory.SECRET),
        (("whatsapp_auth", "creds.json"), PathCategory.SECRET),
        (("webui", "admin.json"), PathCategory.HOST_BOUND),
        (("qdrant", "collection", "_semantic_x", "storage.sqlite"), PathCategory.DATA),  # memory content lives here
        (("instance_archive", "pending.json"), PathCategory.RUNTIME),
        (("inbound_journal.db",), PathCategory.RUNTIME),
        (("data", "subagent_checkpoints.sqlite"), PathCategory.RUNTIME),
        (("subagent_checkpoints.sqlite",), PathCategory.RUNTIME),
        (("snapshots", "snap_1", "data.db"), PathCategory.LOCAL_HISTORY),
        (("some_api_token.json",), PathCategory.SECRET),  # unknown top-level secret-looking name
        (("harness", "oauth_credentials.json"), PathCategory.SECRET),
        (("harness", "workspace", "token-notes.txt"), PathCategory.DATA),  # user content is never second-guessed
        (("wiki", "password-policy.md"), PathCategory.DATA),
        (("harness", "workspace", "app", "node_modules", "a.js"), PathCategory.DERIVED),
        (("skills", "x", ".venv", "bin", "python"), PathCategory.DERIVED),
        (("credentials.json",), PathCategory.SECRET),  # where CredentialsStore keeps channel logins
        ((".myrm", "credentials.json"), PathCategory.SECRET),
        (("wiki", "build.lock"), PathCategory.RUNTIME),
    ],
)
def test_classify_path(parts: tuple[str, ...], category: PathCategory) -> None:
    assert classify_path(parts).category is category


@pytest.mark.parametrize(
    "entry",
    [
        ".encryption_key",
        "webui/admin.json",
        "instance_archive/pending.json",
        "data.db-wal",
        "data/subagent_checkpoints.sqlite",
        "harness/workspace/node_modules/a.js",
        "../escape",
        "wiki/../../escape",
        "./data.db",
        "",
    ],
)
def test_hostile_entries_are_not_importable(entry: str) -> None:
    assert not is_importable_entry(entry)


@pytest.mark.parametrize("entry", ["data.db", "wiki/page.md", "harness/workspace/proj/a.txt", "new_store.db"])
def test_regular_entries_are_importable(entry: str) -> None:
    assert is_importable_entry(entry)


def test_scan_state_dir_splits_carried_and_excluded(source_state: Path) -> None:
    (source_state / "data.db-wal").write_bytes(b"wal")
    os.symlink(source_state / "wiki" / "page.md", source_state / "wiki" / "link.md")

    scan = scan_state_dir(source_state)

    carried = {s.rel for s in scan.sources}
    assert {"data.db", "wiki/page.md", "skills/demo/scripts/run.sh", "unknown_store.db"} <= carried
    assert "harness/workspace/proj/token-notes.txt" in carried
    assert not any(rel.startswith(("webui", "harness/workspace/node_modules")) for rel in carried)
    assert "qdrant/collection/_semantic_memory/storage.sqlite" in carried  # the vector store is carried
    assert ".encryption_key" not in carried
    assert "data.db-wal" not in carried

    excluded_by_rel = {e.rel: e.category for e in scan.excluded}
    assert excluded_by_rel[".encryption_key"] is PathCategory.MACHINE_KEY
    assert excluded_by_rel["session_vault"] is PathCategory.SECRET
    assert excluded_by_rel["webui"] is PathCategory.HOST_BOUND
    assert excluded_by_rel["qdrant/.lock"] is PathCategory.RUNTIME
    assert "wiki/link.md" in excluded_by_rel  # symlinks are never followed
    assert "data.db-wal" not in excluded_by_rel  # sidecars are folded into their database snapshot
    sqlite_flags = {s.rel: s.is_sqlite for s in scan.sources}
    assert sqlite_flags["data.db"] is True
    assert sqlite_flags["wiki/page.md"] is False
    assert scan.unreadable == []


@pytest.mark.skipif(not PERMISSIONS_ENFORCED, reason="needs POSIX permissions that apply to the current user")
def test_scan_reports_a_directory_it_cannot_list_instead_of_dropping_it_silently(source_state: Path) -> None:
    locked = source_state / "wiki" / "private"
    locked.mkdir()
    (locked / "note.md").write_text("kept by nobody")
    locked.chmod(0)
    try:
        scan = scan_state_dir(source_state)
    finally:
        locked.chmod(0o700)

    assert scan.unreadable == ["wiki/private"]
    assert "wiki/private/note.md" not in {s.rel for s in scan.sources}
    assert "wiki/page.md" in {s.rel for s in scan.sources}  # the rest of the tree is still carried


@pytest.mark.skipif(not PERMISSIONS_ENFORCED, reason="needs POSIX permissions that apply to the current user")
def test_scan_reports_a_file_it_can_list_but_not_inspect(source_state: Path) -> None:
    sealed = source_state / "wiki" / "sealed"
    sealed.mkdir()
    (sealed / "note.md").write_text("listed, not inspectable")
    sealed.chmod(0o444)  # names can be read, entries cannot be reached
    try:
        scan = scan_state_dir(source_state)
    finally:
        sealed.chmod(0o700)

    assert scan.unreadable == ["wiki/sealed/note.md"]
    assert "wiki/sealed/note.md" not in {s.rel for s in scan.sources}


def test_scan_does_not_count_a_directory_that_vanished_mid_scan(source_state: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    real_scandir = os.scandir

    def vanishing(path: str | os.PathLike[str]):
        if Path(path) == source_state / "wiki":
            raise FileNotFoundError(path)
        return real_scandir(path)

    monkeypatch.setattr(policy.os, "scandir", vanishing)

    scan = scan_state_dir(source_state)

    assert scan.unreadable == []
    assert "wiki/page.md" not in {s.rel for s in scan.sources}


class _VanishingEntry:
    """A listed file that is gone by the time it is inspected, as in a live instance deleting its own files."""

    def __init__(self, entry: os.DirEntry[str]) -> None:
        self._entry = entry
        self.name = entry.name
        self.path = entry.path

    def is_symlink(self) -> bool:
        return self._entry.is_symlink()

    def is_dir(self, *, follow_symlinks: bool = True) -> bool:
        return self._entry.is_dir(follow_symlinks=follow_symlinks)

    def is_file(self, *, follow_symlinks: bool = True) -> bool:
        return self._entry.is_file(follow_symlinks=follow_symlinks)

    def stat(self) -> os.stat_result:
        raise FileNotFoundError(self.path)


def test_scan_does_not_count_a_file_that_vanished_between_listing_and_inspection(
    source_state: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_scandir = os.scandir

    def listing_with_a_vanishing_file(path: str | os.PathLike[str]) -> list[os.DirEntry[str] | _VanishingEntry]:
        entries = list(real_scandir(path))
        if Path(path) != source_state / "wiki":
            return entries
        return [_VanishingEntry(entry) if entry.name == "page.md" else entry for entry in entries]

    monkeypatch.setattr(policy.os, "scandir", listing_with_a_vanishing_file)

    scan = scan_state_dir(source_state)

    assert scan.unreadable == []
    assert "wiki/page.md" not in {s.rel for s in scan.sources}
    assert "data.db" in {s.rel for s in scan.sources}  # the rest of the tree is still carried
