"""Integration tests: file-edit batch seed fixture + persisted progressSteps."""

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


def _seed(
    client: TestClient, *, variant: str, agent_id: str | None = None
) -> dict[str, object]:
    query = f"variant={variant}"
    if agent_id:
        query += f"&agent_id={agent_id}"
    with patch(
        "app.api.chats.test_fixtures_file_edit_batch.is_local_mode", return_value=True
    ):
        resp = client.post(f"/api/v1/chats/test/seed-file-edit-batch-fixture?{query}")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert str(body["chat_id"]).startswith("e2efedit")
    return body


@pytest.mark.integration
class TestFileEditBatchSeedIntegration:
    def test_live_variant_writes_workspace_file(self, client: TestClient) -> None:
        agent_id = f"agent_{uuid.uuid4().hex[:8]}"
        asyncio.run(_seed_visible_agent(agent_id, display_name="Batch Edit Seed Agent"))

        body = _seed(client, variant="live", agent_id=agent_id)
        file_path = Path(str(body["file_path"]))
        assert file_path.is_file()
        assert file_path.read_text(encoding="utf-8") == "line_a\nline_b\nline_c\n"
        assert body.get("agent_id") == agent_id

        chat_id = str(body["chat_id"])
        messages_resp = client.get(f"/api/v1/chats/{chat_id}/messages")
        assert messages_resp.status_code == 200
        payload = messages_resp.json()["data"]
        messages = payload["messages"]
        roles = [m.get("role") for m in messages if isinstance(m, dict)]
        assert roles.count("assistant") == 0

    def test_read_ui_variant_persists_batch_progress_steps(
        self, client: TestClient
    ) -> None:
        agent_id = f"agent_{uuid.uuid4().hex[:8]}"
        asyncio.run(
            _seed_visible_agent(agent_id, display_name="Batch Edit UI Seed Agent")
        )

        body = _seed(client, variant="read_ui", agent_id=agent_id)
        chat_id = str(body["chat_id"])
        messages_resp = client.get(f"/api/v1/chats/{chat_id}/messages")
        assert messages_resp.status_code == 200
        payload = messages_resp.json()["data"]
        messages = payload["messages"]
        assistant = next(m for m in messages if m.get("role") == "assistant")
        extra = assistant.get("metadata") or {}
        steps = extra.get("progressSteps")
        assert isinstance(steps, list) and steps
        step = steps[0]
        assert step.get("step_key") == "file_edit_tool"
        items = step.get("items")
        assert isinstance(items, list) and items
        diff = str(items[0].get("diff") or "")
        assert "--- edit 1 ---" in diff or "-line_a" in diff

    def test_workspace_only_seed_writes_file_for_existing_chat_id(
        self, client: TestClient
    ) -> None:
        chat_id = f"c-{uuid.uuid4().hex[:12]}"
        with patch(
            "app.api.chats.test_fixtures_file_edit_batch.is_local_mode",
            return_value=True,
        ):
            resp = client.post(
                f"/api/v1/chats/test/seed-file-edit-batch-workspace?chat_id={chat_id}"
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body.get("chat_id") == chat_id
        file_path = Path(str(body["file_path"]))
        assert file_path.is_file()
        assert file_path.read_text(encoding="utf-8") == "line_a\nline_b\nline_c\n"
