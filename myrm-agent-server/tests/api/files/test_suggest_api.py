from __future__ import annotations

from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient
from myrm_agent_harness.toolkits.storage.local import LocalStorageBackend

from app.api.files import suggest
from app.core.storage import FilesService
from app.services.chat.chat_service import ChatService
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
def workspace(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "appChrome.tsx").write_text("export default null")
    (tmp_path / "src" / "components").mkdir()
    return str(tmp_path)


@pytest.fixture(autouse=True)
def chat_workspace(monkeypatch, workspace: str):
    async def get_chat_metadata(chat_id: str):
        return SimpleNamespace(
            id=chat_id,
            workspace_dir=workspace,
            project_id=None,
            agent_id=None,
        )

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


@pytest.mark.anyio
async def test_suggest_uploaded_files_hides_an_incognito_upload_from_other_chats(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch, tmp_path
):
    service = FilesService(LocalStorageBackend(tmp_path / "storage"))
    monkeypatch.setattr(suggest, "files_service", service)
    await service.upload_file("tax-return.pdf", b"x", source_chat_id="chat_incognito")
    await service.upload_file("tax-notes.txt", b"y")

    async def labels(chat_id: str) -> list[str]:
        resp = await client.get("/api/v1/files/suggest", params={"chat_id": chat_id, "q": "tax", "source": "uploaded"})
        assert resp.status_code == 200
        return sorted(item["basename"] for item in resp.json()["data"]["results"])

    assert await labels("chat_incognito") == ["tax-notes.txt", "tax-return.pdf"]
    assert await labels("chat_other") == ["tax-notes.txt"]
