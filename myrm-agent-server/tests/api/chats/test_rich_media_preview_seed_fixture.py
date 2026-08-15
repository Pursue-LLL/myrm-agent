"""Integration tests: rich-media preview seed fixture + browse binary streaming."""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from tests.support.minimal_app import build_minimal_app

app = build_minimal_app("files", preset="chats")


@pytest.fixture
def client(init_test_database) -> TestClient:
    return TestClient(app)


async def _seed_visible_agent(agent_id: str, *, display_name: str) -> None:
    from app.database.models.agent import Agent
    from app.platform_utils import get_session_factory

    session_factory = get_session_factory()
    async with session_factory() as db:
        db.add(
            Agent(
                id=agent_id,
                name=display_name,
                model_selection={"model": "gpt-4o-mini"},
            ),
        )
        await db.commit()


def _seed(client: TestClient, *, agent_id: str) -> dict[str, object]:
    with patch(
        "app.api.chats.test_fixtures.rich_media_preview.is_local_mode",
        return_value=True,
    ):
        resp = client.post(
            "/api/v1/chats/test/seed-rich-media-preview-fixture?agent_id="
            f"{agent_id}"
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert str(body["chat_id"]).startswith("e2ermd")
    return body


def _browse(client: TestClient, workspace: str, path: str) -> object:
    return client.get(
        "/api/v1/files/browse/content",
        params={"path": path, "workspace": workspace},
    )


@pytest.mark.integration
class TestRichMediaPreviewSeedIntegration:
    def test_seed_writes_all_fixture_files(self, client: TestClient) -> None:
        agent_id = f"agent_{uuid.uuid4().hex[:8]}"
        asyncio.run(
            _seed_visible_agent(agent_id, display_name="Rich Media Seed Agent")
        )

        body = _seed(client, agent_id=agent_id)
        workspace_dir = Path(str(body["workspace_dir"]))
        files = body["files"]
        assert isinstance(files, dict)
        assert sorted(files) == ["bundle.zip", "preview.pdf", "preview.png", "readme.txt"]

        from app.api.chats.test_fixtures.rich_media_preview import (
            _minimal_pdf,
            _png_bytes,
        )

        png_path = Path(str(files["preview.png"]))
        assert png_path.read_bytes() == _png_bytes()
        pdf_path = Path(str(files["preview.pdf"]))
        assert pdf_path.read_bytes() == _minimal_pdf()
        zip_path = Path(str(files["bundle.zip"]))
        assert zip_path.read_bytes().startswith(b"PK\x03\x04")
        txt_path = Path(str(files["readme.txt"]))
        assert txt_path.read_text(encoding="utf-8") == "rich media preview E2E fixture\n"
        assert workspace_dir.is_dir()

        chat_id = str(body["chat_id"])
        detail_resp = client.get(f"/api/v1/chats/{chat_id}")
        assert detail_resp.status_code == 200, detail_resp.text
        detail = detail_resp.json()
        chat_payload = detail.get("data", detail)
        chat_obj = chat_payload.get("chat", chat_payload)
        persisted_dir = str(chat_obj.get("workspace_dir") or "")
        assert persisted_dir == str(workspace_dir)

        messages_resp = client.get(f"/api/v1/chats/{chat_id}/messages")
        assert messages_resp.status_code == 200, messages_resp.text
        messages = messages_resp.json()["data"]["messages"]
        roles = [m.get("role") for m in messages if isinstance(m, dict)]
        assert roles.count("user") == 1

    def test_browse_serves_png_inline_with_full_bytes(
        self, client: TestClient
    ) -> None:
        agent_id = f"agent_{uuid.uuid4().hex[:8]}"
        asyncio.run(
            _seed_visible_agent(agent_id, display_name="Rich Media Seed Agent")
        )
        body = _seed(client, agent_id=agent_id)
        workspace = str(body["workspace_dir"])
        file_path = str(body["files"]["preview.png"])

        resp = _browse(client, workspace, file_path)
        assert resp.status_code == 200
        assert resp.headers.get("content-type", "").startswith("image/png")
        assert resp.headers.get("X-Content-Truncated") is None
        assert "inline" in resp.headers.get("content-disposition", "")

        from app.api.chats.test_fixtures.rich_media_preview import _png_bytes

        assert resp.content == _png_bytes()

    def test_browse_serves_pdf_streaming(self, client: TestClient) -> None:
        agent_id = f"agent_{uuid.uuid4().hex[:8]}"
        asyncio.run(
            _seed_visible_agent(agent_id, display_name="Rich Media Seed Agent")
        )
        body = _seed(client, agent_id=agent_id)
        workspace = str(body["workspace_dir"])
        file_path = str(body["files"]["preview.pdf"])

        resp = _browse(client, workspace, file_path)
        assert resp.status_code == 200
        assert resp.headers.get("content-type", "").startswith("application/pdf")
        assert resp.headers.get("X-Content-Truncated") is None
        assert resp.content.startswith(b"%PDF-1.4")
        assert resp.content.endswith(b"%%EOF\n")

    def test_browse_serves_zip_as_stream(self, client: TestClient) -> None:
        agent_id = f"agent_{uuid.uuid4().hex[:8]}"
        asyncio.run(
            _seed_visible_agent(agent_id, display_name="Rich Media Seed Agent")
        )
        body = _seed(client, agent_id=agent_id)
        workspace = str(body["workspace_dir"])
        file_path = str(body["files"]["bundle.zip"])

        resp = _browse(client, workspace, file_path)
        assert resp.status_code == 200
        assert resp.headers.get("X-Content-Truncated") is None
        assert resp.content == b"PK\x03\x04rich-media-preview-placeholder"

    def test_browse_serves_txt_as_inline_text(self, client: TestClient) -> None:
        agent_id = f"agent_{uuid.uuid4().hex[:8]}"
        asyncio.run(
            _seed_visible_agent(agent_id, display_name="Rich Media Seed Agent")
        )
        body = _seed(client, agent_id=agent_id)
        workspace = str(body["workspace_dir"])
        file_path = str(body["files"]["readme.txt"])

        resp = _browse(client, workspace, file_path)
        assert resp.status_code == 200
        assert resp.headers.get("content-type", "").startswith("text/plain")
        assert resp.text == "rich media preview E2E fixture\n"
