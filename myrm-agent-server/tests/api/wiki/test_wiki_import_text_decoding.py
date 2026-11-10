"""Wiki folder, ZIP and Obsidian vault imports read text through the shared decoder: a note in a legacy encoding keeps
its characters, and a file that cannot be read as text is skipped instead of being stored as garbage. An Obsidian
import also reports how many notes it queued, which tells a re-import of unchanged notes apart from a first import."""

from __future__ import annotations

import io
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from myrm_agent_harness.toolkits.wiki.core.structure import WikiStructure

from app.api.wiki.routes.schemas_import import ImportResultResponse, ObsidianImportResultResponse
from app.core.security.auth.identity import LOCAL_USER_ID
from tests.api.wiki.test_wiki_import_raw_gate import _build_import_client

_NOTE = "# 项目路线图\n\n本季度重点：知识库导入、重复内容审核与向量索引重建。每一项都需要负责人与截止日期。\n"
# Not UTF-8, not binary and in no encoding the decoder can identify: storing it would put garbage into raw/.
_UNREADABLE = b"\x80\x81\x82\x83" * 100
_BINARY = bytes(range(256)) * 4


@dataclass(frozen=True, slots=True)
class _Loopback:
    user_id: str = LOCAL_USER_ID
    auth_source: str = "loopback"
    loopback: bool = True
    client_ip: str = "127.0.0.1"
    private_net: bool = False


@pytest.fixture(autouse=True)
def _loopback_caller() -> Iterator[None]:
    with patch("app.middleware.auth.resolve_identity", return_value=_Loopback()):
        yield


@pytest.fixture
def import_client(tmp_path: Path) -> Iterator[tuple[TestClient, WikiStructure]]:
    client, _archiver, structure = _build_import_client(tmp_path)
    yield client, structure
    client.app.dependency_overrides.clear()


def _import_folder(client: TestClient, source_dir: Path, extensions: list[str]) -> ImportResultResponse:
    response = client.post(
        "/api/v1/wiki/import/folder",
        json={"folder_path": str(source_dir), "extensions": extensions, "auto_compile": False, "on_conflict": "skip"},
    )
    assert response.status_code == 200
    return ImportResultResponse.model_validate(response.json())


def _import_vault(client: TestClient, vault: Path) -> ObsidianImportResultResponse:
    response = client.post(
        "/api/v1/wiki/import/obsidian",
        json={"vault_path": str(vault), "auto_compile": False, "on_conflict": "skip"},
    )
    assert response.status_code == 200
    return ObsidianImportResultResponse.model_validate(response.json())


def _zip_of(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return buffer.getvalue()


def test_a_folder_note_in_gbk_keeps_its_characters(import_client: tuple[TestClient, WikiStructure], tmp_path: Path) -> None:
    client, structure = import_client
    source = tmp_path / "source"
    source.mkdir()
    (source / "gbk.md").write_bytes(_NOTE.encode("gbk"))
    (source / "plain.md").write_text("plain note", encoding="utf-8")

    result = _import_folder(client, source, [".md"])

    assert (result.files_scanned, result.files_enqueued) == (2, 2)
    assert structure.get_raw_file_path("gbk.md").read_text(encoding="utf-8") == _NOTE


def test_a_folder_note_with_a_stray_byte_keeps_the_rest_of_its_characters(
    import_client: tuple[TestClient, WikiStructure], tmp_path: Path
) -> None:
    client, structure = import_client
    source = tmp_path / "source"
    source.mkdir()
    (source / "damaged.md").write_bytes(_NOTE.encode("utf-8") + b"\xff")

    result = _import_folder(client, source, [".md"])

    assert result.files_enqueued == 1
    assert structure.get_raw_file_path("damaged.md").read_text(encoding="utf-8") == _NOTE + "\ufffd"


def test_a_folder_file_that_is_not_readable_text_is_skipped(
    import_client: tuple[TestClient, WikiStructure], tmp_path: Path
) -> None:
    client, structure = import_client
    source = tmp_path / "source"
    source.mkdir()
    (source / "unreadable.txt").write_bytes(_UNREADABLE)
    (source / "binary.md").write_bytes(_BINARY)
    (source / "plain.md").write_text("plain note", encoding="utf-8")

    result = _import_folder(client, source, [".md", ".txt"])

    assert (result.files_scanned, result.files_enqueued) == (3, 1)
    assert not structure.get_raw_file_path("unreadable.txt").exists()
    assert not structure.get_raw_file_path("binary.md").exists()
    assert structure.get_raw_file_path("plain.md").read_text(encoding="utf-8") == "plain note"


def test_a_byte_order_mark_and_windows_line_endings_are_not_stored(
    import_client: tuple[TestClient, WikiStructure], tmp_path: Path
) -> None:
    client, structure = import_client
    source = tmp_path / "source"
    source.mkdir()
    (source / "win.md").write_bytes(b"\xef\xbb\xbf# Title\r\nBody\r\n")

    result = _import_folder(client, source, [".md"])

    assert result.files_enqueued == 1
    assert structure.get_raw_file_path("win.md").read_bytes() == b"# Title\nBody\n"


def test_a_zip_import_decodes_gbk_and_skips_what_is_not_readable_text(
    import_client: tuple[TestClient, WikiStructure],
) -> None:
    client, structure = import_client
    archive = _zip_of({"notes/gbk.md": _NOTE.encode("gbk"), "notes/unreadable.md": _UNREADABLE})

    response = client.post(
        "/api/v1/wiki/import/zip",
        params={"extensions": ".md", "auto_compile": "false"},
        files={"file": ("notes.zip", archive, "application/zip")},
    )

    assert response.status_code == 200
    result = ImportResultResponse.model_validate(response.json())
    assert (result.files_scanned, result.files_enqueued) == (2, 1)
    assert structure.get_raw_file_path("notes/gbk.md").read_text(encoding="utf-8") == _NOTE
    assert not structure.get_raw_file_path("notes/unreadable.md").exists()


def test_an_obsidian_note_in_gbk_keeps_its_characters(import_client: tuple[TestClient, WikiStructure], tmp_path: Path) -> None:
    client, structure = import_client
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "gbk.md").write_bytes(_NOTE.encode("gbk"))
    (vault / "plain.md").write_text("plain note", encoding="utf-8")

    result = _import_vault(client, vault)

    assert (result.files_scanned, result.files_processed, result.files_enqueued) == (2, 2, 2)
    assert _NOTE in structure.get_raw_file_path("gbk.md").read_text(encoding="utf-8")


def test_an_obsidian_note_that_is_not_readable_text_is_skipped(
    import_client: tuple[TestClient, WikiStructure], tmp_path: Path
) -> None:
    client, structure = import_client
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "unreadable.md").write_bytes(_UNREADABLE)
    (vault / "plain.md").write_text("plain note", encoding="utf-8")

    result = _import_vault(client, vault)

    assert (result.files_scanned, result.files_processed, result.files_skipped, result.files_enqueued) == (2, 1, 1, 1)
    assert not structure.get_raw_file_path("unreadable.md").exists()


def test_a_vault_imported_again_unchanged_queues_nothing(import_client: tuple[TestClient, WikiStructure], tmp_path: Path) -> None:
    client, _structure = import_client
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "first.md").write_text("first note", encoding="utf-8")
    (vault / "second.md").write_text("second note", encoding="utf-8")

    first = _import_vault(client, vault)
    second = _import_vault(client, vault)

    assert (first.files_processed, first.files_enqueued) == (2, 2)
    assert (second.files_processed, second.files_enqueued) == (2, 0)


def test_an_obsidian_zip_decodes_gbk_and_reports_how_many_notes_it_queued(
    import_client: tuple[TestClient, WikiStructure],
) -> None:
    client, structure = import_client
    archive = _zip_of({"vault/gbk.md": _NOTE.encode("gbk"), "vault/unreadable.md": _UNREADABLE})

    response = client.post(
        "/api/v1/wiki/import/obsidian-zip",
        params={"auto_compile": "false"},
        files={"file": ("vault.zip", archive, "application/zip")},
    )

    assert response.status_code == 200
    result = ObsidianImportResultResponse.model_validate(response.json())
    assert (result.files_scanned, result.files_processed, result.files_skipped, result.files_enqueued) == (2, 1, 1, 1)
    assert _NOTE in structure.get_raw_file_path("gbk.md").read_text(encoding="utf-8")
    assert not structure.get_raw_file_path("unreadable.md").exists()
