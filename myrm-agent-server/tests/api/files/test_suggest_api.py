from __future__ import annotations

from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient

from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="files")
from app.services.chat.chat_service import ChatService


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)  # type: ignore[arg-type]
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
def workspace(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "appChrome.tsx").write_text("export default null")
    (tmp_path / "src" / "components").mkdir()
    return str(tmp_path)


@pytest.fixture(autouse=True)
def chat_workspace(monkeypatch, workspace: str):
    async def get_chat_metadata(chat_id: str):
        return SimpleNamespace(workspace_dir=workspace)

    async def ensure_default_workspace_dir(chat_id: str):
        return workspace

    monkeypatch.setattr(ChatService, "get_chat_metadata", get_chat_metadata)
    monkeypatch.setattr(ChatService, "ensure_default_workspace_dir", ensure_default_workspace_dir)


@pytest.mark.anyio
async def test_suggest_workspace_file_by_camel_boundary(client: AsyncClient):
    resp = await client.get("/api/v1/files/suggest", params={"chat_id": "chat_1", "q": "Chrome"})

    assert resp.status_code == 200
    results = resp.json()["data"]["results"]
    match = next(item for item in results if item["basename"] == "appChrome.tsx")
    assert match["source"] == "workspace"
    assert match["reference_type"] == "workspace_file"
    assert match["relative_path"] == "src/appChrome.tsx"
    assert "path" not in match


@pytest.mark.anyio
async def test_suggest_directory_path_mode(client: AsyncClient):
    resp = await client.get(
        "/api/v1/files/suggest",
        params={"chat_id": "chat_1", "q": "src/", "kind": "directory"},
    )

    assert resp.status_code == 200
    results = resp.json()["data"]["results"]
    assert [item["relative_path"] for item in results] == ["src/components"]
