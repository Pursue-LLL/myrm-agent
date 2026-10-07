"""[POS]: tests/api/memory/test_cvfs_api.py
[INPUT]: FastAPI TestClient, isolated ContextVirtualFileSystem, and CVFS endpoints.
[OUTPUT]: Pytest integration tests verifying virtual file write/read, tree hierarchy, find, and delete operations.
"""

from collections.abc import AsyncGenerator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from myrm_agent_harness.toolkits.memory import (
    ContextVirtualFileSystem,
)

from app.api.memory.cvfs import (
    get_context_vfs,
)
from app.api.memory.cvfs import (
    router as cvfs_router,
)


@pytest.fixture
def isolated_vfs() -> ContextVirtualFileSystem:
    """Create isolated ContextVirtualFileSystem instance backed by in-memory SQLite database."""
    return ContextVirtualFileSystem(db_path=":memory:")


@pytest.fixture
def test_app(isolated_vfs: ContextVirtualFileSystem) -> FastAPI:
    """Create FastAPI test application with injected isolated VFS."""
    api_app = FastAPI()
    api_app.include_router(cvfs_router, prefix="/api/memory")
    api_app.dependency_overrides[get_context_vfs] = lambda: isolated_vfs
    return api_app


@pytest.fixture
async def client(test_app: FastAPI) -> AsyncGenerator[AsyncClient, None]:
    """Async HTTP client fixture bound to isolated test app."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_cvfs_write_and_read_api_flow(client: AsyncClient) -> None:
    """Verify writing context file and deterministically reading with offset slicing."""
    # 1. Write file
    payload = {
        "uri": "ctx://user/preferences/style.md",
        "content": "Prefer concise explanations and clear architectural diagrams.",
        "metadata": {"category": "communication"},
    }
    write_resp = await client.post("/api/memory/cvfs/write", json=payload)
    assert write_resp.status_code == 200
    write_data = write_resp.json()
    assert write_data["uri"] == "ctx://user/preferences/style.md"
    assert write_data["name"] == "style.md"
    assert write_data["node_type"] == "file"
    assert write_data["size_bytes"] == len(payload["content"].encode("utf-8"))

    # 2. Read file full
    read_resp = await client.get("/api/memory/cvfs/read?uri=ctx://user/preferences/style.md")
    assert read_resp.status_code == 200
    read_data = read_resp.json()
    assert read_data["content"] == payload["content"]
    assert read_data["has_more"] is False

    # 3. Read file with slice
    slice_resp = await client.get("/api/memory/cvfs/read?uri=ctx://user/preferences/style.md&offset=0&limit=14")
    assert slice_resp.status_code == 200
    assert slice_resp.json()["content"] == "Prefer concise"
    assert slice_resp.json()["has_more"] is True

    # 4. Read non-existent file returns 404
    missing_resp = await client.get("/api/memory/cvfs/read?uri=ctx://user/preferences/missing.md")
    assert missing_resp.status_code == 404


@pytest.mark.asyncio
async def test_cvfs_ls_and_tree_api_flow(client: AsyncClient) -> None:
    """Verify listing directory contents and rendering ASCII hierarchical tree."""
    # Seed sample files
    await client.post(
        "/api/memory/cvfs/write",
        json={
            "uri": "ctx://resources/project_x/readme.md",
            "content": "# Project X Specification",
        },
    )
    await client.post(
        "/api/memory/cvfs/write",
        json={
            "uri": "ctx://resources/project_x/guidelines.md",
            "content": "# Engineering Guidelines",
        },
    )

    # 1. List directory
    ls_resp = await client.get("/api/memory/cvfs/ls?uri=ctx://resources/project_x")
    assert ls_resp.status_code == 200
    items = ls_resp.json()
    names = [it["name"] for it in items]
    assert "readme.md" in names
    assert "guidelines.md" in names

    # 2. Render tree
    tree_resp = await client.get("/api/memory/cvfs/tree?uri=ctx://&max_depth=3")
    assert tree_resp.status_code == 200
    tree_data = tree_resp.json()
    assert tree_data["total_nodes"] >= 5
    assert "resources/" in tree_data["rendered_tree"]
    assert "project_x/" in tree_data["rendered_tree"]
    assert "readme.md" in tree_data["rendered_tree"]


@pytest.mark.asyncio
async def test_cvfs_mkdir_find_and_delete_api_flow(client: AsyncClient) -> None:
    """Verify creating directory, searching nodes by keyword, and recursive deletion."""
    # 1. Mkdir
    mkdir_resp = await client.post(
        "/api/memory/cvfs/mkdir",
        json={"uri": "ctx://artifacts/sess_999", "metadata": {"session": "999"}},
    )
    assert mkdir_resp.status_code == 200
    assert mkdir_resp.json()["name"] == "sess_999"
    assert mkdir_resp.json()["node_type"] == "directory"

    # Write file inside
    await client.post(
        "/api/memory/cvfs/write",
        json={
            "uri": "ctx://artifacts/sess_999/benchmark_report.md",
            "content": "QPS: 15000, P99: 1.2ms latency",
        },
    )

    # 2. Find keyword
    find_resp = await client.post(
        "/api/memory/cvfs/find",
        json={"keyword": "benchmark", "prefix_uri": "ctx://artifacts"},
    )
    assert find_resp.status_code == 200
    find_data = find_resp.json()
    assert find_data["total"] >= 1
    assert any(m["name"] == "benchmark_report.md" for m in find_data["matches"])

    # 3. Delete directory recursively
    del_resp = await client.delete("/api/memory/cvfs/node?uri=ctx://artifacts/sess_999")
    assert del_resp.status_code == 200
    assert del_resp.json()["deleted"] is True

    # 4. Verify file is deleted
    read_del = await client.get("/api/memory/cvfs/read?uri=ctx://artifacts/sess_999/benchmark_report.md")
    assert read_del.status_code == 404
