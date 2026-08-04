"""Integration tests: workspace-merge seed fixture + persisted workspaceMergeFailures."""

from __future__ import annotations

import asyncio
import uuid
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
class TestWorkspaceMergeSeedIntegration:
    def test_batch_merge_fail_variant_persists_merge_failures(
        self, client: TestClient
    ) -> None:
        agent_id = f"agent_{uuid.uuid4().hex[:8]}"
        asyncio.run(_seed_visible_agent(agent_id, display_name="Merge Seed Agent"))

        with patch(
            "app.api.chats.test_fixtures_workspace_merge.is_local_mode",
            return_value=True,
        ):
            resp = client.post(
                "/api/v1/chats/test/seed-workspace-merge-fixture?variant=batch_merge_fail"
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        chat_id = str(body["chat_id"])
        assert chat_id.startswith("e2ewsmr")

        messages_resp = client.get(f"/api/v1/chats/{chat_id}/messages")
        assert messages_resp.status_code == 200, messages_resp.text
        payload = messages_resp.json()["data"]
        messages = payload["messages"]
        assistant = next(
            (
                msg
                for msg in messages
                if isinstance(msg, dict) and msg.get("role") == "assistant"
            ),
            None,
        )
        assert assistant is not None
        metadata = assistant.get("metadata") or {}
        failures = metadata.get("workspaceMergeFailures")
        assert isinstance(failures, list) and len(failures) == 1
        assert "task_index=1" in str(failures[0].get("message") or "")
        assert metadata.get("workspaceMergeFailedCount") == 1
        assert metadata.get("completionStatus") == "warning"
