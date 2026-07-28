"""Tests for workspace file watch registration API."""

from __future__ import annotations

import os

import pytest
from httpx import ASGITransport, AsyncClient

from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="files")


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)  # type: ignore[arg-type]
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
def workspace_dir(tmp_path):
    (tmp_path / "readme.md").write_text("# Hello", encoding="utf-8")
    return str(tmp_path)


@pytest.fixture(autouse=True)
async def cleanup_watch_service():
    yield
    from app.services.workspace.file_watch_service import get_workspace_file_watch_service

    await get_workspace_file_watch_service().release_all()


@pytest.mark.anyio
async def test_register_workspace_watch(client: AsyncClient, workspace_dir: str):
    resp = await client.post("/api/v1/files/browse/watch", json={"workspace": workspace_dir})
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["workspace"] == os.path.realpath(workspace_dir)

    delete_resp = await client.delete(
        "/api/v1/files/browse/watch",
        params={"workspace": workspace_dir},
    )
    assert delete_resp.status_code == 200


@pytest.mark.anyio
async def test_register_workspace_watch_rejects_dangerous_path(client: AsyncClient):
    resp = await client.post("/api/v1/files/browse/watch", json={"workspace": "/etc"})
    assert resp.status_code in (400, 422)


@pytest.mark.anyio
async def test_register_workspace_watch_rejects_missing_dir(client: AsyncClient):
    resp = await client.post(
        "/api/v1/files/browse/watch",
        json={"workspace": "/nonexistent_workspace_watch_xyz"},
    )
    assert resp.status_code in (400, 422)
