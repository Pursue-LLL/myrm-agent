"""Tests for POST /migration/upload — Cloud ZIP upload migration bridge."""

from __future__ import annotations

import io
import zipfile

import pytest
from httpx import ASGITransport, AsyncClient

from tests.support.minimal_app import build_minimal_app


@pytest.fixture()
def app():
    return build_minimal_app("migration_upload")


@pytest.fixture()
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


def _make_zip(files: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return buf.getvalue()


@pytest.mark.asyncio
async def test_upload_rejects_non_zip(client: AsyncClient):
    resp = await client.post(
        "/api/v1/migration/upload",
        files={"file": ("data.txt", b"hello", "text/plain")},
    )
    assert resp.status_code == 400
    assert "zip" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_upload_rejects_invalid_zip(client: AsyncClient):
    resp = await client.post(
        "/api/v1/migration/upload",
        files={"file": ("data.zip", b"not-a-zip", "application/zip")},
    )
    assert resp.status_code == 400
    assert "Invalid" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_upload_rejects_path_traversal(client: AsyncClient):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("../../etc/passwd", "root:x:0:0")
    payload = buf.getvalue()
    resp = await client.post(
        "/api/v1/migration/upload",
        files={"file": ("evil.zip", payload, "application/zip")},
    )
    assert resp.status_code == 400
    assert "unsafe" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_upload_empty_zip_returns_empty_sources(client: AsyncClient):
    payload = _make_zip({"readme.txt": "nothing here"})
    resp = await client.post(
        "/api/v1/migration/upload",
        files={"file": ("empty.zip", payload, "application/zip")},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["sources"] == []
    assert data["available"] is True
    assert data["scan_path"] == "upload"


@pytest.mark.asyncio
async def test_upload_hermes_data_detected(client: AsyncClient):
    payload = _make_zip({
        ".hermes/config.yaml": "model: gpt-4",
        ".hermes/SOUL.md": "You are helpful.",
        ".hermes/memories/MEMORY.md": "- Likes Python\n- Works at Acme",
    })
    resp = await client.post(
        "/api/v1/migration/upload",
        files={"file": ("hermes.zip", payload, "application/zip")},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["available"] is True
    sources = data["sources"]
    assert len(sources) >= 1
    hermes = next((s for s in sources if s["competitor"] == "hermes"), None)
    assert hermes is not None
    assert hermes["memory_count_estimate"] >= 2


@pytest.mark.asyncio
async def test_upload_openclaw_data_detected(client: AsyncClient):
    import json

    payload = _make_zip({
        ".openclaw/memory.json": json.dumps([{"content": "Prefers concise answers"}]),
        ".openclaw/sessions.json": json.dumps([{"title": "Test", "summary": "A test session"}]),
    })
    resp = await client.post(
        "/api/v1/migration/upload",
        files={"file": ("openclaw.zip", payload, "application/zip")},
    )
    assert resp.status_code == 200
    data = resp.json()
    sources = data["sources"]
    assert len(sources) >= 1
    oc = next((s for s in sources if s["competitor"] == "openclaw"), None)
    assert oc is not None
