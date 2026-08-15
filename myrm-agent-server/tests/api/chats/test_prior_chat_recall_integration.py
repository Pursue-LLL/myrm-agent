"""Integration test: prior_chat recall SSOT seed → GET /recall/search → inject path.

[INPUT]
tests.support.minimal_app::build_minimal_app (POS: 按需挂载 API 路由的测试 app)
app.api.chats.test_fixtures.prior_chat::seed_prior_chat_fixture (POS: @chat E2E seed)

[OUTPUT]
TestPriorChatRecallIntegration: HTTP recall search matches seeded prior chat index.

[POS]
Chats API 集成测。验证 @chat picker SSOT（/recall/search）与 inject 共用 recall 索引（真 DB，无 mock）。
"""

from __future__ import annotations

import asyncio
import uuid
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.services.agent.params.models import MentionReferenceRequest
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


class TestPriorChatRecallIntegration:
    """Verify recall search API returns seeded prior chat and inject resolves it."""

    def test_recall_search_returns_seeded_prior_chat(self, client: TestClient) -> None:
        agent_id = f"agent_{uuid.uuid4().hex[:8]}"
        asyncio.run(
            _seed_visible_agent(
                agent_id, display_name="Prior Chat Recall Integration Agent"
            )
        )

        with patch(
            "app.api.chats.test_fixtures.prior_chat.is_local_mode", return_value=True
        ):
            seed_resp = client.post("/api/v1/chats/test/seed-prior-chat-fixture")

        assert seed_resp.status_code == 200
        seed_body = seed_resp.json()
        prior_chat_id = str(seed_body["prior_chat_id"])
        composer_chat_id = str(seed_body["composer_chat_id"])
        assert prior_chat_id.startswith("e2eprior")
        assert composer_chat_id.startswith("e2ecomp")

        search_resp = client.get(
            "/api/v1/chats/recall/search",
            params={"q": "Alpha", "limit": 20, "exclude_chat_id": composer_chat_id},
        )
        assert search_resp.status_code == 200
        payload = search_resp.json()["data"]
        items = payload["items"]
        assert payload["total"] >= 1
        assert any(item["chat_id"] == prior_chat_id for item in items)

    def test_prior_chat_inject_resolves_seeded_recall_document(
        self, client: TestClient
    ) -> None:
        from app.services.agent.params.mention import _build_mention_reference_context

        agent_id = f"agent_{uuid.uuid4().hex[:8]}"
        asyncio.run(
            _seed_visible_agent(
                agent_id, display_name="Prior Chat Inject Integration Agent"
            )
        )

        with patch(
            "app.api.chats.test_fixtures.prior_chat.is_local_mode", return_value=True
        ):
            seed_resp = client.post("/api/v1/chats/test/seed-prior-chat-fixture")

        assert seed_resp.status_code == 200
        prior_chat_id = str(seed_resp.json()["prior_chat_id"])

        context, warnings, tokens = asyncio.run(
            _build_mention_reference_context(
                [
                    MentionReferenceRequest(
                        type="prior_chat",
                        path=prior_chat_id,
                        label="@chat:Alpha project",
                    )
                ],
                "/tmp/workspace",
            )
        )

        assert 'type="prior-chat"' in context
        assert "Alpha project" in context or "Redis" in context
        assert warnings == []
        assert tokens > 0
