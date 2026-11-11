"""Wiki clip form parsing: whole pages as form text fields, the route's own 8 MB guard, and forms that cannot be read.

The browser extension posts the page as multipart text parts (``html`` / ``markdown``): ``files=[(name, (None, value))]``
builds such a part, while a tuple with a file name is an uploaded asset. ``data=`` alone posts an urlencoded form.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import patch

import pytest
from starlette.types import ASGIApp, Message, Scope

from app.services.wiki.clip import MAX_CLIP_PAYLOAD_BYTES, clip_form_payload_bytes
from tests.support.wiki_clip_client import (
    build_wiki_client,
    bypass_loopback_auth,
    cleanup_wiki_client,
    poll_clip_job,
)

_STARLETTE_PART_LIMIT_BYTES = 1024 * 1024
_PAGE_LINE = "clipped line " * 6 + "\n"

_CLIP_FORM = {
    "source_url": "https://example.com/page",
    "title": "Page",
    "clip_mode": "full_page",
    "queue_compile": "false",
}


@pytest.fixture(autouse=True)
def _bypass_auth() -> Iterator[None]:
    with bypass_loopback_auth():
        yield


async def _post_upload_aborted_after_first_chunk(app: ASGIApp) -> list[int]:
    """Drive the clip route with a multipart body whose client disconnects mid-upload; returns the response statuses."""
    messages: list[Message] = [
        {
            "type": "http.request",
            "body": b'--xx\r\nContent-Disposition: form-data; name="markdown"\r\n\r\npartial page',
            "more_body": True,
        },
        {"type": "http.disconnect"},
    ]
    sent: list[Message] = []

    async def receive() -> Message:
        return messages.pop(0) if messages else {"type": "http.disconnect"}

    async def send(message: Message) -> None:
        sent.append(message)

    scope: Scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/api/v1/wiki/clip",
        "raw_path": b"/api/v1/wiki/clip",
        "root_path": "",
        "query_string": b"",
        "headers": [(b"content-type", b"multipart/form-data; boundary=xx"), (b"host", b"testserver")],
        "client": ("127.0.0.1", 50000),
        "server": ("testserver", 80),
    }
    await app(scope, receive, send)
    return [message["status"] for message in sent if message["type"] == "http.response.start"]


def test_wiki_clip_accepts_a_text_part_above_the_parser_default_limit(tmp_path: Path) -> None:
    page = _PAGE_LINE * (_STARLETTE_PART_LIMIT_BYTES // len(_PAGE_LINE) + 1) + "# end of page\n"
    assert len(page) > _STARLETTE_PART_LIMIT_BYTES
    client, _archiver, structure = build_wiki_client(tmp_path)
    try:
        with patch("app.services.wiki.dedup_runner.schedule_wiki_dedup_scan", return_value=None):
            response = client.post("/api/v1/wiki/clip", data=_CLIP_FORM, files=[("markdown", (None, page))])
            assert response.status_code == 202
            final = poll_clip_job(client, response.json()["job_id"])
        assert final["state"] == "succeeded"
        stored = structure.get_raw_file_path(str(final["relative_path"])).read_text(encoding="utf-8")
        assert "# end of page" in stored
    finally:
        cleanup_wiki_client(client)


def test_wiki_clip_rejects_an_oversize_text_part_with_413(tmp_path: Path) -> None:
    client, _archiver, _structure = build_wiki_client(tmp_path)
    try:
        oversize_page = "x" * (MAX_CLIP_PAYLOAD_BYTES + 1)
        response = client.post("/api/v1/wiki/clip", data=_CLIP_FORM, files=[("markdown", (None, oversize_page))])
        assert response.status_code == 413
    finally:
        cleanup_wiki_client(client)


def test_wiki_clip_rejects_an_oversize_urlencoded_field_with_413(tmp_path: Path) -> None:
    client, _archiver, _structure = build_wiki_client(tmp_path)
    try:
        oversize_page = "x" * (MAX_CLIP_PAYLOAD_BYTES + 1)
        response = client.post("/api/v1/wiki/clip", data={**_CLIP_FORM, "html": oversize_page})
        assert response.status_code == 413
    finally:
        cleanup_wiki_client(client)


def test_wiki_clip_rejects_an_oversize_asset_with_413(tmp_path: Path) -> None:
    client, _archiver, _structure = build_wiki_client(tmp_path)
    try:
        oversize_asset = b"x" * (MAX_CLIP_PAYLOAD_BYTES + 1)
        response = client.post(
            "/api/v1/wiki/clip",
            data={**_CLIP_FORM, "asset_urls": json.dumps(["https://example.com/huge.bin"])},
            files=[("asset_files", ("asset.bin", oversize_asset, "application/octet-stream"))],
        )
        assert response.status_code == 413
    finally:
        cleanup_wiki_client(client)


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


def test_wiki_clip_keeps_the_parser_message_for_a_form_without_boundary(tmp_path: Path) -> None:
    client, _archiver, _structure = build_wiki_client(tmp_path)
    try:
        response = client.post(
            "/api/v1/wiki/clip",
            content=b"no boundary announced",
            headers={"content-type": "multipart/form-data"},
        )
        assert response.status_code == 400
        assert "boundary" in response.json()["detail"].lower()
    finally:
        cleanup_wiki_client(client)


def test_wiki_clip_answers_an_aborted_upload_with_400(tmp_path: Path) -> None:
    client, _archiver, _structure = build_wiki_client(tmp_path)
    try:
        assert asyncio.run(_post_upload_aborted_after_first_chunk(client.app)) == [400]
    finally:
        cleanup_wiki_client(client)
