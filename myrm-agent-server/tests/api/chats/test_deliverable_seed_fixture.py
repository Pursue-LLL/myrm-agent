"""Integration tests: deliverable link seed fixture."""

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
class TestDeliverableLinkSeedIntegration:
    def test_seed_creates_workspace_file_and_deliverable_markdown(self, client: TestClient, tmp_path: Path) -> None:
        agent_id = f"agent_{uuid.uuid4().hex[:8]}"
        asyncio.run(_seed_visible_agent(agent_id, display_name="Deliverable Seed Agent"))

        workspace = tmp_path / "workspace"
        workspace.mkdir()

        async def _fake_resolve(chat_id: str, *, persist_workspace: bool = False) -> str:
            _ = chat_id, persist_workspace
            return str(workspace)

        with (
            patch(
                "app.api.chats.test_fixtures.deliverable.is_local_mode",
                return_value=True,
            ),
            patch(
                "app.api.chats.test_fixtures.deliverable.resolve_default_chat_workspace_dir",
                side_effect=_fake_resolve,
            ),
            patch(
                "app.api.chats.test_fixtures.deliverable.AgentService.get_agent_list",
                return_value=([type("A", (), {"id": agent_id})()], 1),
            ),
        ):
            resp = client.post("/api/v1/chats/test/seed-deliverable-link-fixture")

        assert resp.status_code == 200, resp.text
        body = resp.json()
        chat_id = str(body["chat_id"])
        deliverable_path = str(body["deliverable_path"])
        assert chat_id.startswith("e2edeliv")
        assert deliverable_path == "workspace/deliverable_e2e.md"

        file_on_disk = workspace / "deliverable_e2e.md"
        assert file_on_disk.is_file()
        assert "Deliverable E2E" in file_on_disk.read_text(encoding="utf-8")

        messages_resp = client.get(f"/api/v1/chats/{chat_id}/messages")
        assert messages_resp.status_code == 200, messages_resp.text
        messages = messages_resp.json()["data"]["messages"]
        assistant = next(m for m in messages if m["role"] == "assistant")
        assert deliverable_path in assistant["content"]
