from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="chats")


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


class TestChatsEmbedSeedFixture:
    """HTTP tests for local-only link embed Chrome E2E seed endpoint (no LLM)."""

    def test_seed_embed_fixture_http_endpoint(self, client: TestClient) -> None:
        fake_agent = MagicMock()
        fake_agent.id = "agent-e2e-embed"
        fake_agent.display_name = "Embed E2E Agent"

        with (
            patch("app.api.chats.test_fixtures.is_local_mode", return_value=True),
            patch(
                "app.api.chats.test_fixtures.AgentService.get_agent_list",
                new_callable=AsyncMock,
                return_value=([fake_agent], 1),
            ),
            patch(
                "app.api.chats.test_fixtures.ChatService.create_or_update_chat",
                new_callable=AsyncMock,
            ),
            patch(
                "app.api.chats.test_fixtures.ChatService.append_message",
                new_callable=AsyncMock,
            ) as append_message,
        ):
            resp = client.post("/api/v1/chats/test/seed-embed-fixture")

        assert resp.status_code == 200
        body = resp.json()
        chat_id = body["chat_id"]
        assert chat_id.startswith("e2eembed")
        assert body["agent_id"] == "agent-e2e-embed"
        assert "dQw4w9WgXcQ" in str(body["youtube_url"])
        assert body["ui_path"] == f"/{chat_id}"
        assert append_message.await_count == 2

    def test_seed_embed_fixture_hidden_outside_local_mode(self, client: TestClient) -> None:
        with patch("app.api.chats.test_fixtures.is_local_mode", return_value=False):
            resp = client.post("/api/v1/chats/test/seed-embed-fixture")
        assert resp.status_code == 404
