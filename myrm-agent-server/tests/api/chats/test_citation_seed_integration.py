"""Integration test: citation seed fixture persists citedMemoryIds through HTTP + DB."""

from __future__ import annotations

import asyncio
import uuid
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="chats")


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


class TestCitationSeedIntegration:
    """Verify seed endpoint writes assistant message metadata to the database."""

    def test_seed_persists_cited_memory_ids(self, client: TestClient) -> None:
        agent_id = f"agent_{uuid.uuid4().hex[:8]}"
        asyncio.run(_seed_visible_agent(agent_id, display_name="Citation Seed Integration Agent"))

        with patch("app.api.chats.test_fixtures.is_local_mode", return_value=True):
            seed_resp = client.post("/api/v1/chats/test/seed-citation-fixture")

        assert seed_resp.status_code == 200
        seed_body = seed_resp.json()
        chat_id = str(seed_body["chat_id"])
        assert chat_id.startswith("e2ewiki")
        assert seed_body["citation_count"] == 10

        messages_resp = client.get(f"/api/v1/chats/{chat_id}/messages")
        assert messages_resp.status_code == 200
        payload = messages_resp.json()["data"]
        messages = payload["messages"]
        assistant_messages = [item for item in messages if item["role"] == "assistant"]
        assert len(assistant_messages) == 1

        metadata = assistant_messages[0]["metadata"]
        cited_ids = metadata["citedMemoryIds"]
        cited_refs = metadata["citedMemoryRefs"]
        assert len(cited_ids) == 10
        assert cited_ids[0] == "e2e-cite-1"
        assert len(cited_refs) == 10
        assert cited_refs[0]["id"] == "e2e-cite-1"
