"""Wiki import endpoints — raw publication gate integration tests."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from myrm_agent_harness.toolkits.wiki.core.structure import WikiStructure

from app.core.security.auth.identity import LOCAL_USER_ID
from app.services.wiki.memory_to_wiki import MemoryToWikiArchiver
from tests.support.minimal_app import build_minimal_app


@pytest.fixture(autouse=True)
def _bypass_auth() -> None:
    from dataclasses import dataclass

    @dataclass(frozen=True, slots=True)
    class _FakeIdentity:
        user_id: str = LOCAL_USER_ID
        auth_source: str = "loopback"
        loopback: bool = True
        client_ip: str = "127.0.0.1"
        private_net: bool = False

    with patch(
        "app.middleware.auth.resolve_identity",
        return_value=_FakeIdentity(),
    ):
        yield


def _build_import_client(tmp_path: Path) -> tuple[TestClient, MemoryToWikiArchiver, WikiStructure]:
    from app.api.wiki.router import _get_wiki_archiver

    archiver = MemoryToWikiArchiver(MagicMock(), wiki_dir=str(tmp_path / "wiki"))
    structure = archiver._structure
    structure.ensure_structure()

    app = build_minimal_app(preset="wiki")

    async def _override_archiver() -> MemoryToWikiArchiver:
        return archiver

    app.dependency_overrides[_get_wiki_archiver] = _override_archiver
    return TestClient(app), archiver, structure


def test_import_folder_skips_conflicting_raw(tmp_path: Path) -> None:
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    (source_dir / "note.md").write_text("import version", encoding="utf-8")

    client, _archiver, structure = _build_import_client(tmp_path)
    existing = structure.get_raw_file_path("note.md")
    existing.parent.mkdir(parents=True, exist_ok=True)
    existing.write_text("existing version", encoding="utf-8")

    try:
        response = client.post(
            "/api/v1/wiki/import/folder",
            json={
                "folder_path": str(source_dir),
                "extensions": [".md"],
                "auto_compile": False,
                "on_conflict": "skip",
            },
        )
    finally:
        client.app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert data["files_skipped_conflict"] == 1
    assert data["conflict_paths"] == ["note.md"]
    assert existing.read_text(encoding="utf-8") == "existing version"


def test_import_folder_supersede_requires_reason(tmp_path: Path) -> None:
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    (source_dir / "note.md").write_text("import version", encoding="utf-8")

    client, _archiver, structure = _build_import_client(tmp_path)
    existing = structure.get_raw_file_path("note.md")
    existing.parent.mkdir(parents=True, exist_ok=True)
    existing.write_text("existing version", encoding="utf-8")

    try:
        response = client.post(
            "/api/v1/wiki/import/folder",
            json={
                "folder_path": str(source_dir),
                "extensions": [".md"],
                "auto_compile": False,
                "on_conflict": "supersede",
                "supersede_reason": "",
            },
        )
    finally:
        client.app.dependency_overrides.clear()

    assert response.status_code == 422
    assert existing.read_text(encoding="utf-8") == "existing version"


def test_import_folder_supersede_writes_and_audits(tmp_path: Path) -> None:
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    (source_dir / "note.md").write_text("import version", encoding="utf-8")

    client, _archiver, structure = _build_import_client(tmp_path)
    existing = structure.get_raw_file_path("note.md")
    existing.parent.mkdir(parents=True, exist_ok=True)
    existing.write_text("existing version", encoding="utf-8")

    try:
        response = client.post(
            "/api/v1/wiki/import/folder",
            json={
                "folder_path": str(source_dir),
                "extensions": [".md"],
                "auto_compile": False,
                "on_conflict": "supersede",
                "supersede_reason": "Re-import from settings",
            },
        )
    finally:
        client.app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert data["files_superseded"] == 1
    assert existing.read_text(encoding="utf-8") == "import version"
    log_text = structure.get_log_file_path().read_text(encoding="utf-8")
    assert "Superseded raw source" in log_text


def test_import_folder_blocks_credential_content(tmp_path: Path) -> None:
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    secret = "sk-1234567890abcdefghijklmnopqrstuvwxyz1234567890abcd"
    (source_dir / "note.md").write_text(f"OPENAI_API_KEY={secret}", encoding="utf-8")

    client, _archiver, structure = _build_import_client(tmp_path)

    try:
        response = client.post(
            "/api/v1/wiki/import/folder",
            json={
                "folder_path": str(source_dir),
                "extensions": [".md"],
                "auto_compile": False,
                "on_conflict": "skip",
            },
        )
    finally:
        client.app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert data["files_security_blocked"] == 1
    assert data["security_blocked_paths"] == ["note.md"]
    assert not structure.get_raw_file_path("note.md").exists()
