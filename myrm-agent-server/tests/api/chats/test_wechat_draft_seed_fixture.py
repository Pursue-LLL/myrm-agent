"""Integration tests: WeChat draft seed fixture."""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from tests.support.minimal_app import build_minimal_app

app = build_minimal_app("chats", preset="chats")


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


@pytest.mark.integration
def test_seed_wechat_draft_fixture_creates_html_artifact(client: TestClient, tmp_path: Path) -> None:
    agent_id = f"agent_{uuid.uuid4().hex[:8]}"
    asyncio.run(_seed_visible_agent(agent_id, display_name="WeChat Draft Seed Agent"))

    workspace = tmp_path / "workspace"
    workspace.mkdir()

    async def _fake_resolve(chat_id: str, *, persist_workspace: bool = False) -> str:
        _ = chat_id, persist_workspace
        return str(workspace)

    with (
        patch("app.api.chats.test_fixtures_wechat_draft.is_local_mode", return_value=True),
        patch(
            "app.api.chats.test_fixtures_wechat_draft.resolve_default_chat_workspace_dir",
            side_effect=_fake_resolve,
        ),
        patch(
            "app.api.chats.test_fixtures_wechat_draft.AgentService.get_agent_list",
            return_value=([type("A", (), {"id": agent_id})()], 1),
        ),
    ):
        resp = client.post("/api/v1/chats/test/seed-wechat-draft-fixture?variant=compliance_block")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    chat_id = str(body["chat_id"])
    assert chat_id.startswith("e2ewxd")
    assert (workspace / "article.wechat.html").is_file()
    assert (workspace / "cover.png").is_file()

    messages_resp = client.get(f"/api/v1/chats/{chat_id}/messages")
    assert messages_resp.status_code == 200, messages_resp.text
    messages = messages_resp.json()["data"]["messages"]
    assistant = next(m for m in messages if m["role"] == "assistant")
    metadata = assistant.get("metadata") or {}
    artifacts = metadata.get("artifacts")
    assert isinstance(artifacts, list) and artifacts
    assert artifacts[0]["filename"] == "article.wechat.html"
    assert artifacts[0]["type"] == "html"
