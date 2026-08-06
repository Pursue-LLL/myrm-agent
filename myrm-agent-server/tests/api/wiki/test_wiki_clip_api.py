"""Wiki clip + wikiignore API tests."""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from myrm_agent_harness.toolkits.wiki.core.structure import WikiStructure

from app.core.security.auth.identity import LOCAL_USER_ID
from app.services.wiki.memory_to_wiki import MemoryToWikiArchiver
from tests.support.minimal_app import build_minimal_app


@dataclass(frozen=True, slots=True)
class _FakeIdentity:
    user_id: str = LOCAL_USER_ID
    auth_source: str = "loopback"
    loopback: bool = True
    client_ip: str = "127.0.0.1"
    private_net: bool = False


@pytest.fixture(autouse=True)
def _bypass_auth() -> None:
    with patch(
        "app.middleware.auth.resolve_identity",
        return_value=_FakeIdentity(),
    ):
        yield


def _build_wiki_client(tmp_path: Path) -> tuple[TestClient, MemoryToWikiArchiver, WikiStructure]:
    from app.api.wiki.router import _get_wiki_archiver

    archiver = MemoryToWikiArchiver(MagicMock(), wiki_dir=str(tmp_path / "wiki"))
    structure = archiver._structure
    structure.ensure_structure()

    app = build_minimal_app(preset="wiki")

    async def _override_archiver() -> MemoryToWikiArchiver:
        return archiver

    app.dependency_overrides[_get_wiki_archiver] = _override_archiver
    return TestClient(app), archiver, structure


def test_wikiignore_get_and_put(tmp_path: Path) -> None:
    client, _archiver, structure = _build_wiki_client(tmp_path)
    try:
        empty = client.get("/api/v1/wiki/wikiignore")
        assert empty.status_code == 200
        assert empty.json()["content"] == ""

        updated = client.put(
            "/api/v1/wiki/wikiignore",
            json={"content": "drafts/**\n*.tmp\n"},
        )
        assert updated.status_code == 200
        assert "drafts/**" in updated.json()["content"]

        again = client.get("/api/v1/wiki/wikiignore")
        assert again.status_code == 200
        assert "drafts/**" in again.json()["content"]
        assert structure.load_wikiignore_patterns() == ("drafts/**", "*.tmp")
    finally:
        client.app.dependency_overrides.clear()


def test_wiki_clip_accepts_and_writes_raw(tmp_path: Path) -> None:
    client, _archiver, structure = _build_wiki_client(tmp_path)
    try:
        with patch("app.services.wiki.clip_runner.schedule_wiki_dedup_scan", return_value=None):
            response = client.post(
                "/api/v1/wiki/clip",
                data={
                    "source_url": "https://example.com/article",
                    "title": "Test Article",
                    "clip_mode": "full_page",
                    "markdown": "# Test\n\nHello from clip.",
                    "queue_compile": "false",
                },
            )
        assert response.status_code == 202
        job_id = response.json()["job_id"]
        assert job_id

        final = None
        for _ in range(40):
            status = client.get(f"/api/v1/wiki/clip/{job_id}")
            assert status.status_code == 200
            final = status.json()
            if final["state"] in {"succeeded", "failed"}:
                break
            time.sleep(0.05)

        assert final is not None
        assert final["state"] == "succeeded"
        assert final["written"] is True
        rel_path = final["relative_path"]
        assert rel_path
        raw_path = structure.get_raw_file_path(rel_path)
        assert raw_path.is_file()
        assert "Hello from clip." in raw_path.read_text(encoding="utf-8")
    finally:
        client.app.dependency_overrides.clear()


def test_wiki_clip_job_not_found(tmp_path: Path) -> None:
    client, _, _ = _build_wiki_client(tmp_path)
    try:
        response = client.get("/api/v1/wiki/clip/does-not-exist")
        assert response.status_code == 404
    finally:
        client.app.dependency_overrides.clear()
