"""Wiki URL and video import endpoints — raw publication gate integration tests."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from myrm_agent_harness.core.security.guards.ssrf import SSRFResult

from app.core.security.auth.identity import LOCAL_USER_ID
from tests.api.wiki.test_wiki_import_raw_gate import _build_import_client


@dataclass(frozen=True, slots=True)
class _FakeIdentity:
    user_id: str = LOCAL_USER_ID
    auth_source: str = "loopback"
    loopback: bool = True
    client_ip: str = "127.0.0.1"
    private_net: bool = False


@pytest.fixture(autouse=True)
def _bypass_auth() -> Iterator[None]:
    with patch(
        "app.middleware.auth.resolve_identity",
        return_value=_FakeIdentity(),
    ):
        yield


def test_import_urls_success(tmp_path: Path) -> None:
    client, _archiver, structure = _build_import_client(tmp_path)

    with (
        patch(
            "myrm_agent_harness.core.security.guards.ssrf.async_validate_url_for_ssrf",
            new=AsyncMock(return_value=SSRFResult(safe=True)),
        ),
        patch(
            "myrm_agent_harness.toolkits.wiki.fetch_url_markdown",
            return_value="# Test Title\n\nArticle body content.",
        ),
    ):
        try:
            response = client.post(
                "/api/v1/wiki/import/urls",
                json={
                    "urls": ["https://example.com/article-1"],
                    "folder_path": "Articles/Web",
                    "auto_compile": False,
                    "on_conflict": "skip",
                },
            )
        finally:
            client.app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["total_urls"] == 1
    assert data["enqueued_count"] == 1
    assert data["results"][0]["status"] == "success"
    assert data["results"][0]["error_code"] is None
    assert data["results"][0]["url"] == "https://example.com/article-1"
    rel_path = data["results"][0]["relative_path"]
    assert rel_path.lower().startswith("articles/web/")
    raw_path = structure.get_raw_file_path(rel_path)
    assert raw_path.is_file()
    content = raw_path.read_text(encoding="utf-8")
    assert "https://example.com/article-1" in content
    assert "Article body content." in content


def test_import_urls_ssrf_blocked(tmp_path: Path) -> None:
    client, _archiver, _structure = _build_import_client(tmp_path)

    try:
        response = client.post(
            "/api/v1/wiki/import/urls",
            json={
                "urls": ["http://127.0.0.1:8000/internal-secrets"],
                "auto_compile": False,
                "on_conflict": "skip",
            },
        )
    finally:
        client.app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["error_count"] == 1
    assert data["enqueued_count"] == 0
    assert data["results"][0]["status"] == "error"
    assert data["results"][0]["error"] == "This address cannot be imported"
    assert data["results"][0]["error_code"] == "address_rejected"


def test_import_urls_conflict_skip_and_supersede(tmp_path: Path) -> None:
    client, _archiver, structure = _build_import_client(tmp_path)

    with (
        patch(
            "myrm_agent_harness.core.security.guards.ssrf.async_validate_url_for_ssrf",
            new=AsyncMock(return_value=SSRFResult(safe=True)),
        ),
        patch(
            "myrm_agent_harness.toolkits.wiki.fetch_url_markdown",
            return_value="# Version 1\n\nFirst edition.",
        ),
    ):
        try:
            resp1 = client.post(
                "/api/v1/wiki/import/urls",
                json={
                    "urls": ["https://example.com/shared-doc"],
                    "auto_compile": False,
                    "on_conflict": "skip",
                },
            )
        finally:
            pass

    assert resp1.status_code == 200
    data1 = resp1.json()
    assert data1["enqueued_count"] == 1
    rel_path = data1["results"][0]["relative_path"]
    raw_file = structure.get_raw_file_path(rel_path)
    assert "First edition." in raw_file.read_text(encoding="utf-8")

    # Conflict skip
    with (
        patch(
            "myrm_agent_harness.core.security.guards.ssrf.async_validate_url_for_ssrf",
            new=AsyncMock(return_value=SSRFResult(safe=True)),
        ),
        patch(
            "myrm_agent_harness.toolkits.wiki.fetch_url_markdown",
            return_value="# Version 2\n\nSecond edition.",
        ),
    ):
        try:
            resp2 = client.post(
                "/api/v1/wiki/import/urls",
                json={
                    "urls": ["https://example.com/shared-doc"],
                    "auto_compile": False,
                    "on_conflict": "skip",
                },
            )
        finally:
            pass

    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["skipped_conflict_count"] == 1
    assert data2["results"][0]["status"] == "skipped_conflict"
    assert "First edition." in raw_file.read_text(encoding="utf-8")

    # Supersede
    with (
        patch(
            "myrm_agent_harness.core.security.guards.ssrf.async_validate_url_for_ssrf",
            new=AsyncMock(return_value=SSRFResult(safe=True)),
        ),
        patch(
            "myrm_agent_harness.toolkits.wiki.fetch_url_markdown",
            return_value="# Version 2\n\nSecond edition.",
        ),
    ):
        try:
            resp3 = client.post(
                "/api/v1/wiki/import/urls",
                json={
                    "urls": ["https://example.com/shared-doc"],
                    "auto_compile": False,
                    "on_conflict": "supersede",
                    "supersede_reason": "Updated from upstream website",
                },
            )
        finally:
            client.app.dependency_overrides.clear()

    assert resp3.status_code == 200
    data3 = resp3.json()
    assert data3["superseded_count"] == 1
    assert data3["results"][0]["status"] == "superseded"
    assert "Second edition." in raw_file.read_text(encoding="utf-8")


def test_import_urls_redacts_credential_content(tmp_path: Path) -> None:
    client, _archiver, structure = _build_import_client(tmp_path)
    secret = "sk-1234567890abcdefghijklmnopqrstuvwxyz1234567890abcd"

    with (
        patch(
            "myrm_agent_harness.core.security.guards.ssrf.async_validate_url_for_ssrf",
            new=AsyncMock(return_value=SSRFResult(safe=True)),
        ),
        patch(
            "myrm_agent_harness.toolkits.wiki.fetch_url_markdown",
            return_value=f"# Leaked Page\n\nOPENAI_API_KEY={secret}",
        ),
    ):
        try:
            response = client.post(
                "/api/v1/wiki/import/urls",
                json={
                    "urls": ["https://example.com/leak"],
                    "auto_compile": False,
                    "on_conflict": "skip",
                },
            )
        finally:
            client.app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert data["security_redacted_count"] == 1 and data["security_blocked_count"] == 0
    assert data["enqueued_count"] == 1
    result = data["results"][0]
    assert result["status"] == "security_redacted"
    stored = structure.get_raw_file_path(result["relative_path"]).read_text(encoding="utf-8")
    assert secret not in stored and "[REDACTED:" in stored


def test_import_video_bilibili_success(tmp_path: Path) -> None:
    from langchain_core.documents import Document

    client, archiver, structure = _build_import_client(tmp_path)
    fake_doc = Document(
        page_content="00:00 Welcome\n00:30 System Architecture Design",
        metadata={
            "title": "Clean Arch Video",
            "author_name": "Software Guru",
            "duration": "10:00",
            "bvid": "BV1xx411c7Xz",
        },
    )

    with (
        patch(
            "myrm_agent_harness.core.security.guards.ssrf.async_validate_url_for_ssrf",
            new=AsyncMock(return_value=SSRFResult(safe=True)),
        ),
        patch(
            "myrm_agent_harness.toolkits.wiki.pipeline.ingress.video_ingress.extract_bilibili_subtitle",
            new=AsyncMock(return_value=fake_doc),
        ),
    ):
        try:
            response = client.post(
                "/api/v1/wiki/import/video",
                json={
                    "url": "https://www.bilibili.com/video/BV1xx411c7Xz",
                    "folder_path": "videos",
                    "auto_compile": False,
                    "on_conflict": "skip",
                },
            )
        finally:
            client.app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["status"] == "success"
    assert data["error_code"] is None
    rel_path = data["relative_path"]
    assert rel_path.lower().startswith("videos/")
    raw_path = structure.get_raw_file_path(rel_path)
    assert raw_path.is_file()
    content = raw_path.read_text(encoding="utf-8")
    assert "Clean Arch Video" in content
    assert "Software Guru" in content


def test_import_video_ssrf_blocked(tmp_path: Path) -> None:
    client, _archiver, _structure = _build_import_client(tmp_path)

    try:
        response = client.post(
            "/api/v1/wiki/import/video",
            json={
                "url": "http://127.0.0.1:8000/internal-video",
                "folder_path": "videos",
                "auto_compile": False,
                "on_conflict": "skip",
            },
        )
    finally:
        client.app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is False
    assert data["status"] == "error"
    assert (data["error"], data["error_code"]) == ("This address cannot be imported", "address_rejected")
