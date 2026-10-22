"""Uploads bound to an incognito chat stay out of every export, whether or not their chat still has a row.

An upload travels with a chat the archive keeps: the test is the chat's state, not the binding alone, so an upload
bound to a chat that is not incognito stays in the backup and only the export's own rule decides, regardless of how
the binding was made.

The files are written by the real ``FilesService`` on the layout the runtime uses, so a change of the key layout or of
the sidecar format breaks these tests instead of silently putting incognito uploads back into backups.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import zipfile
from dataclasses import dataclass
from pathlib import Path

import pytest
from myrm_agent_harness.toolkits.storage.config import StorageConfig
from myrm_agent_harness.toolkits.storage.local import LocalStorageBackend

from app.core.storage import FilesService
from app.core.storage.chat_bound import pdf_extract_source
from app.services.instance_archive import export_service
from app.services.instance_archive.export_service import ExportError, build_export
from app.services.instance_archive.incognito_uploads import STORAGE_REL, without_incognito_uploads
from app.services.instance_archive.policy import SourceFile, StateScan

SECRET = b"incognito_upload_secret_bytes"
KEPT = b"ordinary_upload_bytes"
_PAYLOAD_DIR = "payload/"


@dataclass(frozen=True)
class Seeded:
    """File ids of one seeded instance, by role."""

    incognito_upload: str
    incognito_page_image: str
    abandoned_upload: str
    switched_off_upload: str
    ordinary_upload: str
    generated: str


def _seed(state: Path) -> Seeded:
    conn = sqlite3.connect(state / "data.db")
    conn.executescript(
        """
        CREATE TABLE _schema_migrations (version INTEGER);
        INSERT INTO _schema_migrations VALUES (1);
        CREATE TABLE chats (id TEXT PRIMARY KEY, is_incognito BOOLEAN, source TEXT);
        INSERT INTO chats VALUES ('incognito', 1, 'web'), ('switched-off', 0, 'web');
        """
    )
    conn.commit()
    conn.close()

    async def write() -> Seeded:
        service = FilesService(LocalStorageBackend(state / STORAGE_REL))
        incognito = await service.upload_file("tax.pdf", SECRET, source_chat_id="incognito")
        page_image = await service.save_generated_file(
            "pdf-page-1.png", SECRET, "image/png", source_chat_id=pdf_extract_source(incognito.id)
        )
        # The chat of this upload was never persisted: no row names it, yet it is still an incognito upload.
        abandoned = await service.upload_file("draft.pdf", SECRET, source_chat_id="never-persisted")
        # Bound to a chat the archive keeps, so it travels: the rule follows the chat's state, not the binding.
        switched_off = await service.upload_file("contract.pdf", KEPT, source_chat_id="switched-off")
        ordinary = await service.upload_file("notes.txt", KEPT)
        generated = await service.save_generated_file("report.md", KEPT, source_chat_id="chat-ordinary")
        return Seeded(incognito.id, page_image.id, abandoned.id, switched_off.id, ordinary.id, generated.id)

    return asyncio.run(write())


def _export(state: Path, dest: Path) -> dict[str, bytes]:
    result = build_export(
        state_dir=state, dest=dest, user_id="u", app_version="1.0.0", deploy_mode="local", config_key=None, passphrase=None
    )
    with zipfile.ZipFile(result.path) as archive:
        return {
            name.removeprefix(_PAYLOAD_DIR): archive.read(name) for name in archive.namelist() if name.startswith(_PAYLOAD_DIR)
        }


def _members_about(members: dict[str, bytes], file_id: str) -> list[str]:
    return [name for name in members if file_id in name]


def test_an_incognito_upload_its_page_images_and_an_abandoned_upload_are_not_exported(tmp_path: Path) -> None:
    state = tmp_path / "state"
    state.mkdir()
    seeded = _seed(state)

    members = _export(state, tmp_path / "out.zip")

    for gone in (seeded.incognito_upload, seeded.incognito_page_image, seeded.abandoned_upload):
        assert _members_about(members, gone) == [], "the content and the sidecar of an incognito upload must both stay out"
    assert [name for name, data in members.items() if SECRET in data] == []


def test_every_file_of_a_chat_the_archive_keeps_still_travels_with_its_sidecar(tmp_path: Path) -> None:
    state = tmp_path / "state"
    state.mkdir()
    seeded = _seed(state)

    members = _export(state, tmp_path / "out.zip")

    for kept in (seeded.switched_off_upload, seeded.ordinary_upload, seeded.generated):
        assert len(_members_about(members, kept)) == 2  # the content and its .meta.json


def test_an_unreadable_sidecar_takes_its_file_out_and_is_reported_instead_of_guessed_at(tmp_path: Path) -> None:
    folder = tmp_path / "locked.meta.json"
    folder.mkdir()  # reading a directory fails the way a permission error does, without needing a privileged test run
    content = f"{STORAGE_REL}/files/uploads/locked"
    scan = StateScan(
        sources=[
            SourceFile(f"{content}.meta.json", folder, 1, False),
            SourceFile(content, tmp_path / "locked", 1, False),
            SourceFile("data.db", tmp_path / "data.db", 1, True),
        ],
        excluded=[],
        unreadable=[],
    )

    result = without_incognito_uploads(scan, [])

    assert [source.rel for source in result.sources] == ["data.db"]
    assert result.unreadable == [f"{content}.meta.json", content]


def test_a_corrupt_sidecar_is_carried_because_nothing_ties_it_to_a_chat(tmp_path: Path) -> None:
    sidecar = tmp_path / "broken.meta.json"
    sidecar.write_text("{not json", encoding="utf-8")
    rel = f"{STORAGE_REL}/files/uploads/broken.meta.json"
    scan = StateScan(sources=[SourceFile(rel, sidecar, 9, False)], excluded=[], unreadable=[])

    assert [source.rel for source in without_incognito_uploads(scan, []).sources] == [rel]


def test_an_export_that_cannot_tell_which_chats_it_keeps_fails_instead_of_carrying_every_bound_upload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def unreadable(_main_db: Path) -> set[str]:
        raise sqlite3.OperationalError("database is locked")

    state = tmp_path / "state"
    state.mkdir()
    _seed(state)
    monkeypatch.setattr(export_service, "live_surviving_chat_ids", unreadable)

    with pytest.raises(ExportError):
        _export(state, tmp_path / "out.zip")
    assert not (tmp_path / "out.zip").exists()


def test_the_file_store_sits_where_the_runtime_creates_it(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MYRM_DATA_DIR", str(tmp_path))

    assert StorageConfig().get_base_path() == (tmp_path / STORAGE_REL).resolve()

    async def stored() -> Path:
        service = FilesService(LocalStorageBackend(tmp_path / STORAGE_REL))
        saved = await service.upload_file("a.txt", b"a", source_chat_id="c")
        return tmp_path / STORAGE_REL / "files" / "uploads" / f"{saved.id}.meta.json"

    sidecar = asyncio.run(stored())
    assert json.loads(sidecar.read_text(encoding="utf-8"))["source_chat_id"] == "c"
