"""Wiki clip + wikiignore API tests."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from myrm_agent_harness.toolkits.wiki.core.structure import WikiStructure

from app.core.security.auth.identity import LOCAL_USER_ID
from app.services.wiki.clip import MAX_CLIP_PAYLOAD_BYTES, clip_form_payload_bytes
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


def _build_wiki_client(
    tmp_path: Path,
) -> tuple[TestClient, MemoryToWikiArchiver, WikiStructure]:
    from app.api.wiki.router import _get_wiki_archiver

    archiver = MemoryToWikiArchiver(MagicMock(), wiki_dir=str(tmp_path / "wiki"))
    structure = archiver._structure
    structure.ensure_structure()

    app = build_minimal_app(preset="wiki")

    async def _override_archiver() -> MemoryToWikiArchiver:
        return archiver

    app.dependency_overrides[_get_wiki_archiver] = _override_archiver
    patcher = patch(
        "app.services.wiki.vault.get_wiki_archiver",
        return_value=archiver,
    )
    patcher.start()
    client = TestClient(app)
    client._wiki_archiver_patcher = patcher  # type: ignore[attr-defined]
    return client, archiver, structure


def _cleanup_wiki_client(client: TestClient) -> None:
    client.app.dependency_overrides.clear()
    patcher = getattr(client, "_wiki_archiver_patcher", None)
    if patcher is not None:
        patcher.stop()


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
        _cleanup_wiki_client(client)


def _poll_clip_job(client: TestClient, job_id: str) -> dict[str, object]:
    final: dict[str, object] | None = None
    for _ in range(40):
        status = client.get(f"/api/v1/wiki/clip/{job_id}")
        assert status.status_code == 200
        final = status.json()
        if final["state"] in {"succeeded", "failed"}:
            return final
        time.sleep(0.05)
    raise AssertionError(f"clip job timed out: {final}")


def test_wiki_clip_accepts_and_writes_raw(tmp_path: Path) -> None:
    client, _archiver, structure = _build_wiki_client(tmp_path)
    try:
        with patch("app.services.wiki.dedup_runner.schedule_wiki_dedup_scan", return_value=None):
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

        final = _poll_clip_job(client, job_id)

        assert final["state"] == "succeeded"
        assert final["written"] is True
        rel_path = final["relative_path"]
        assert rel_path
        raw_path = structure.get_raw_file_path(rel_path)
        assert raw_path.is_file()
        assert "Hello from clip." in raw_path.read_text(encoding="utf-8")
    finally:
        _cleanup_wiki_client(client)


def test_wiki_clip_queue_compile_false_string(tmp_path: Path) -> None:
    client, archiver, structure = _build_wiki_client(tmp_path)
    try:
        with patch("app.services.wiki.dedup_runner.schedule_wiki_dedup_scan", return_value=None):
            response = client.post(
                "/api/v1/wiki/clip",
                data={
                    "source_url": "https://example.com/no-compile",
                    "title": "No Compile",
                    "clip_mode": "full_page",
                    "markdown": "# No compile",
                    "queue_compile": "false",
                },
            )
        assert response.status_code == 202
        job_id = response.json()["job_id"]

        final = None
        for _ in range(40):
            status = client.get(f"/api/v1/wiki/clip/{job_id}")
            final = status.json()
            if final["state"] in {"succeeded", "failed"}:
                break
            time.sleep(0.05)

        assert final is not None
        assert final["state"] == "succeeded"
        assert archiver._queue.get_stats()["pending"] == 0
    finally:
        _cleanup_wiki_client(client)


def test_wiki_clip_queue_compile_true_enqueues_raw(tmp_path: Path) -> None:
    client, archiver, _structure = _build_wiki_client(tmp_path)
    try:
        with (
            patch(
                "app.services.wiki.dedup_runner.schedule_wiki_dedup_scan",
                return_value=None,
            ),
            patch.object(archiver._compiler, "start_background_worker") as start_worker,
        ):
            response = client.post(
                "/api/v1/wiki/clip",
                data={
                    "source_url": "https://example.com/auto-compile",
                    "title": "Auto Compile",
                    "clip_mode": "full_page",
                    "markdown": "# Auto compile\n\nQueue compile after clip.",
                    "queue_compile": "true",
                },
            )
        assert response.status_code == 202
        final = _poll_clip_job(client, response.json()["job_id"])
        assert final["state"] == "succeeded"
        assert final["written"] is True
        assert archiver._queue.get_stats()["pending"] == 1
        start_worker.assert_called_once()
    finally:
        _cleanup_wiki_client(client)


def test_wiki_clip_payload_too_large(tmp_path: Path) -> None:
    client, _, _ = _build_wiki_client(tmp_path)
    try:
        huge = "x" * (MAX_CLIP_PAYLOAD_BYTES + 1)
        response = client.post(
            "/api/v1/wiki/clip",
            data={
                "source_url": "https://example.com/huge",
                "title": "Huge",
                "clip_mode": "full_page",
                "markdown": huge,
                "queue_compile": "false",
            },
        )
        assert response.status_code == 413
    finally:
        _cleanup_wiki_client(client)


def test_wiki_clip_payload_bytes_counts_asset_urls_field() -> None:
    small_body = {
        "source_url": "https://example.com/small-body",
        "title": "Small",
        "clip_mode": "full_page",
        "html": "",
        "markdown": "# Small",
        "folder_path": "",
        "queue_compile": "false",
    }
    huge_asset_urls = json.dumps([f"https://example.com/{'a' * (MAX_CLIP_PAYLOAD_BYTES + 1)}"])
    payload_bytes = clip_form_payload_bytes(
        **small_body,
        asset_urls=huge_asset_urls,
        asset_file_bytes=(b"x",),
    )
    assert payload_bytes > MAX_CLIP_PAYLOAD_BYTES


def test_wiki_clip_job_not_found(tmp_path: Path) -> None:
    client, _, _ = _build_wiki_client(tmp_path)
    try:
        response = client.get("/api/v1/wiki/clip/does-not-exist")
        assert response.status_code == 404
    finally:
        _cleanup_wiki_client(client)


def test_wiki_clip_html_path_writes_raw(tmp_path: Path) -> None:
    client, _archiver, structure = _build_wiki_client(tmp_path)
    try:
        with patch("app.services.wiki.dedup_runner.schedule_wiki_dedup_scan", return_value=None):
            response = client.post(
                "/api/v1/wiki/clip",
                data={
                    "source_url": "https://example.com/html-article",
                    "title": "HTML Article",
                    "clip_mode": "full_page",
                    "html": "<article><h1>HTML Title</h1><p>Body from HTML path.</p></article>",
                    "markdown": "",
                    "queue_compile": "false",
                },
            )
        assert response.status_code == 202
        final = _poll_clip_job(client, response.json()["job_id"])
        assert final["state"] == "succeeded"
        assert final["written"] is True
        rel_path = str(final["relative_path"])
        raw_path = structure.get_raw_file_path(rel_path)
        content = raw_path.read_text(encoding="utf-8")
        assert "Body from HTML path." in content
    finally:
        _cleanup_wiki_client(client)


def test_wiki_clip_custom_folder_path_writes_raw(tmp_path: Path) -> None:
    client, _archiver, structure = _build_wiki_client(tmp_path)
    try:
        with patch("app.services.wiki.dedup_runner.schedule_wiki_dedup_scan", return_value=None):
            response = client.post(
                "/api/v1/wiki/clip",
                data={
                    "source_url": "https://example.com/custom-folder",
                    "title": "Custom Folder Clip",
                    "clip_mode": "full_page",
                    "markdown": "# Custom folder\n\nWritten under clips/manual.",
                    "folder_path": "clips/manual",
                    "queue_compile": "false",
                },
            )
        assert response.status_code == 202
        final = _poll_clip_job(client, response.json()["job_id"])
        assert final["state"] == "succeeded"
        assert final["written"] is True
        rel_path = str(final["relative_path"])
        assert rel_path.startswith("clips/manual/")
        assert rel_path.endswith(".md")
        raw_path = structure.get_raw_file_path(rel_path)
        assert raw_path.is_file()
        assert "Custom folder" in raw_path.read_text(encoding="utf-8")
    finally:
        _cleanup_wiki_client(client)


def test_wiki_clip_conflict_job_response(tmp_path: Path) -> None:
    client, _archiver, structure = _build_wiki_client(tmp_path)
    try:
        rel = "clips/manual/existing.md"
        existing = structure.get_raw_file_path(rel)
        existing.parent.mkdir(parents=True, exist_ok=True)
        existing.write_text("existing content", encoding="utf-8")

        with patch("app.services.wiki.dedup_runner.schedule_wiki_dedup_scan", return_value=None):
            response = client.post(
                "/api/v1/wiki/clip",
                data={
                    "source_url": "https://example.com/conflict",
                    "title": "Existing",
                    "clip_mode": "selection",
                    "markdown": "# New clip",
                    "folder_path": "clips/manual",
                    "queue_compile": "false",
                },
            )
        assert response.status_code == 202
        final = _poll_clip_job(client, response.json()["job_id"])
        assert final["state"] == "succeeded"
        assert final["written"] is False
        assert final["conflict"] is True
        assert existing.read_text(encoding="utf-8") == "existing content"
    finally:
        _cleanup_wiki_client(client)


def test_wiki_clip_publishes_ingest_snapshot_on_write(tmp_path: Path) -> None:
    client, _archiver, structure = _build_wiki_client(tmp_path)
    try:
        with (
            patch(
                "app.services.wiki.dedup_runner.schedule_wiki_dedup_scan",
                return_value=None,
            ),
            patch(
                "app.services.wiki.ingest_events.publish_wiki_ingest_snapshot",
                new_callable=AsyncMock,
            ) as publish_snapshot,
        ):
            response = client.post(
                "/api/v1/wiki/clip",
                data={
                    "source_url": "https://example.com/sse-refresh",
                    "title": "SSE Refresh",
                    "clip_mode": "full_page",
                    "markdown": "# SSE\n\nClip should publish ingest snapshot.",
                    "queue_compile": "false",
                },
            )
        assert response.status_code == 202
        final = _poll_clip_job(client, response.json()["job_id"])
        assert final["state"] == "succeeded"
        assert final["written"] is True
        publish_snapshot.assert_awaited_once()
    finally:
        _cleanup_wiki_client(client)


def test_wiki_clip_security_blocked_job_response(tmp_path: Path) -> None:
    client, _archiver, structure = _build_wiki_client(tmp_path)
    secret = "sk-1234567890abcdefghijklmnopqrstuvwxyz1234567890abcd"
    try:
        with patch("app.services.wiki.dedup_runner.schedule_wiki_dedup_scan", return_value=None):
            response = client.post(
                "/api/v1/wiki/clip",
                data={
                    "source_url": "https://example.com/credential-block",
                    "title": "Credential Block",
                    "clip_mode": "full_page",
                    "markdown": f"# Secret\n\nOPENAI_API_KEY={secret}\n",
                    "queue_compile": "false",
                },
            )
        assert response.status_code == 202
        final = _poll_clip_job(client, response.json()["job_id"])
        assert final["state"] == "succeeded"
        assert final["written"] is False
        assert final["security_blocked"] is True
        rel_path = str(final.get("relative_path", ""))
        if rel_path:
            assert not structure.get_raw_file_path(rel_path).exists()
    finally:
        _cleanup_wiki_client(client)


def test_wiki_clip_multipart_assets(tmp_path: Path) -> None:
    client, _archiver, structure = _build_wiki_client(tmp_path)
    try:
        png_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
        with patch("app.services.wiki.dedup_runner.schedule_wiki_dedup_scan", return_value=None):
            response = client.post(
                "/api/v1/wiki/clip",
                data={
                    "source_url": "https://example.com/with-asset",
                    "title": "Asset Clip",
                    "clip_mode": "full_page",
                    "markdown": "![alt](https://example.com/img.png)",
                    "asset_urls": json.dumps(["https://example.com/img.png"]),
                    "queue_compile": "false",
                },
                files=[("asset_files", ("asset.bin", png_bytes, "image/png"))],
            )
        assert response.status_code == 202
        final = _poll_clip_job(client, response.json()["job_id"])
        assert final["state"] == "succeeded"
        assert final["written"] is True
        rel_path = str(final["relative_path"])
        content = structure.get_raw_file_path(rel_path).read_text(encoding="utf-8")
        assert "wiki/assets/" in content or "assets/" in content
    finally:
        _cleanup_wiki_client(client)


def test_wiki_clip_reclip_same_source_url_replaces_raw(tmp_path: Path) -> None:
    client, _archiver, structure = _build_wiki_client(tmp_path)
    source_url = "https://example.com/reclip-api"
    try:
        with patch("app.services.wiki.dedup_runner.schedule_wiki_dedup_scan", return_value=None):
            first = client.post(
                "/api/v1/wiki/clip",
                data={
                    "source_url": source_url,
                    "title": "Reclip API",
                    "clip_mode": "full_page",
                    "markdown": "# Version 1\n",
                    "queue_compile": "false",
                },
            )
        assert first.status_code == 202
        first_final = _poll_clip_job(client, first.json()["job_id"])
        assert first_final["written"] is True
        rel_path = str(first_final["relative_path"])

        with patch("app.services.wiki.dedup_runner.schedule_wiki_dedup_scan", return_value=None):
            second = client.post(
                "/api/v1/wiki/clip",
                data={
                    "source_url": source_url,
                    "title": "Reclip API",
                    "clip_mode": "full_page",
                    "markdown": "# Version 2\n",
                    "queue_compile": "false",
                },
            )
        assert second.status_code == 202
        second_final = _poll_clip_job(client, second.json()["job_id"])
        assert second_final["written"] is True
        assert second_final.get("conflict") is not True
        assert str(second_final["relative_path"]) == rel_path
        content = structure.get_raw_file_path(rel_path).read_text(encoding="utf-8")
        assert "Version 2" in content
    finally:
        _cleanup_wiki_client(client)
