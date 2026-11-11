"""Wiki clip + wikiignore API tests."""

from __future__ import annotations

import json
import time
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from tests.support.wiki_clip_client import (
    build_wiki_client,
    bypass_loopback_auth,
    cleanup_wiki_client,
    poll_clip_job,
)


@pytest.fixture(autouse=True)
def _bypass_auth() -> Iterator[None]:
    with bypass_loopback_auth():
        yield


def test_wikiignore_get_and_put(tmp_path: Path) -> None:
    client, _archiver, structure = build_wiki_client(tmp_path)
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
        cleanup_wiki_client(client)


def test_wiki_clip_accepts_and_writes_raw(tmp_path: Path) -> None:
    client, _archiver, structure = build_wiki_client(tmp_path)
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

        final = poll_clip_job(client, job_id)

        assert final["state"] == "succeeded"
        assert final["written"] is True
        rel_path = final["relative_path"]
        assert rel_path
        raw_path = structure.get_raw_file_path(rel_path)
        assert raw_path.is_file()
        assert "Hello from clip." in raw_path.read_text(encoding="utf-8")
    finally:
        cleanup_wiki_client(client)


def test_wiki_clip_queue_compile_false_string(tmp_path: Path) -> None:
    client, archiver, structure = build_wiki_client(tmp_path)
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
        cleanup_wiki_client(client)


def test_wiki_clip_queue_compile_true_enqueues_raw(tmp_path: Path) -> None:
    client, archiver, _structure = build_wiki_client(tmp_path)
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
        final = poll_clip_job(client, response.json()["job_id"])
        assert final["state"] == "succeeded"
        assert final["written"] is True
        assert archiver._queue.get_stats()["pending"] == 1
        start_worker.assert_called_once()
    finally:
        cleanup_wiki_client(client)


def test_wiki_clip_job_not_found(tmp_path: Path) -> None:
    client, _, _ = build_wiki_client(tmp_path)
    try:
        response = client.get("/api/v1/wiki/clip/does-not-exist")
        assert response.status_code == 404
    finally:
        cleanup_wiki_client(client)


def test_wiki_clip_html_path_writes_raw(tmp_path: Path) -> None:
    client, _archiver, structure = build_wiki_client(tmp_path)
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
        final = poll_clip_job(client, response.json()["job_id"])
        assert final["state"] == "succeeded"
        assert final["written"] is True
        rel_path = str(final["relative_path"])
        raw_path = structure.get_raw_file_path(rel_path)
        content = raw_path.read_text(encoding="utf-8")
        assert "Body from HTML path." in content
    finally:
        cleanup_wiki_client(client)


def test_wiki_clip_custom_folder_path_writes_raw(tmp_path: Path) -> None:
    client, _archiver, structure = build_wiki_client(tmp_path)
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
        final = poll_clip_job(client, response.json()["job_id"])
        assert final["state"] == "succeeded"
        assert final["written"] is True
        rel_path = str(final["relative_path"])
        assert rel_path.startswith("clips/manual/")
        assert rel_path.endswith(".md")
        raw_path = structure.get_raw_file_path(rel_path)
        assert raw_path.is_file()
        assert "Custom folder" in raw_path.read_text(encoding="utf-8")
    finally:
        cleanup_wiki_client(client)


def test_wiki_clip_conflict_job_response(tmp_path: Path) -> None:
    client, _archiver, structure = build_wiki_client(tmp_path)
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
        final = poll_clip_job(client, response.json()["job_id"])
        assert final["state"] == "succeeded"
        assert final["written"] is False
        assert final["conflict"] is True
        assert existing.read_text(encoding="utf-8") == "existing content"
    finally:
        cleanup_wiki_client(client)


def test_wiki_clip_publishes_ingest_snapshot_on_write(tmp_path: Path) -> None:
    client, _archiver, structure = build_wiki_client(tmp_path)
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
        final = poll_clip_job(client, response.json()["job_id"])
        assert final["state"] == "succeeded"
        assert final["written"] is True
        publish_snapshot.assert_awaited_once()
    finally:
        cleanup_wiki_client(client)


def test_wiki_clip_redacts_credential_content(tmp_path: Path) -> None:
    client, _archiver, structure = build_wiki_client(tmp_path)
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
        final = poll_clip_job(client, response.json()["job_id"])
        assert final["state"] == "succeeded"
        assert final["written"] is True and final["security_blocked"] is False
        stored = structure.get_raw_file_path(str(final["relative_path"])).read_text(encoding="utf-8")
        assert secret not in stored and "[REDACTED:" in stored
    finally:
        cleanup_wiki_client(client)


def test_wiki_clip_multipart_assets(tmp_path: Path) -> None:
    client, _archiver, structure = build_wiki_client(tmp_path)
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
        final = poll_clip_job(client, response.json()["job_id"])
        assert final["state"] == "succeeded"
        assert final["written"] is True
        rel_path = str(final["relative_path"])
        content = structure.get_raw_file_path(rel_path).read_text(encoding="utf-8")
        assert "wiki/assets/" in content or "assets/" in content
    finally:
        cleanup_wiki_client(client)


def test_wiki_clip_reclip_same_source_url_replaces_raw(tmp_path: Path) -> None:
    client, _archiver, structure = build_wiki_client(tmp_path)
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
        first_final = poll_clip_job(client, first.json()["job_id"])
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
        second_final = poll_clip_job(client, second.json()["job_id"])
        assert second_final["written"] is True
        assert second_final.get("conflict") is not True
        assert str(second_final["relative_path"]) == rel_path
        content = structure.get_raw_file_path(rel_path).read_text(encoding="utf-8")
        assert "Version 2" in content
    finally:
        cleanup_wiki_client(client)
