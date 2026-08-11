"""HTTP tests for local-only SecurityPreset Chrome E2E seed endpoint (no LLM)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="chats")


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


class TestSecurityPresetSeedFixture:
    """Verify seed-security-preset-fixture route mounting, guards and payload."""

    def test_seed_security_preset_fixture_http_endpoint(self, client: TestClient) -> None:
        preset_agent = MagicMock()
        preset_agent.id = "agent-e2e-sec-preset"
        plain_agent = MagicMock()
        plain_agent.id = "agent-e2e-sec-plain"
        explore_agent = MagicMock()
        explore_agent.id = "agent-e2e-sec-explore"

        with (
            patch(
                "app.api.chats.test_fixtures_security_preset.is_local_mode",
                return_value=True,
            ),
            patch(
                "app.api.chats.test_fixtures_security_preset.AgentService.create_agent",
                new_callable=AsyncMock,
                side_effect=[preset_agent, plain_agent, explore_agent],
            ),
            patch(
                "app.api.chats.test_fixtures_security_preset.ChatService.create_or_update_chat",
                new_callable=AsyncMock,
            ) as create_chat,
        ):
            resp = client.post("/api/v1/chats/test/seed-security-preset-fixture")

        assert resp.status_code == 200
        body = resp.json()
        preset_chat_id = body["preset_chat_id"]
        plain_chat_id = body["plain_chat_id"]
        explore_chat_id = body["explore_chat_id"]
        assert preset_chat_id.startswith("e2esecpreset")
        assert plain_chat_id.startswith("e2esecpreset")
        assert explore_chat_id.startswith("e2esecpreset")
        assert body["preset_agent_id"] == "agent-e2e-sec-preset"
        assert body["plain_agent_id"] == "agent-e2e-sec-plain"
        assert body["explore_agent_id"] == "agent-e2e-sec-explore"
        assert body["preset_ui_path"] == f"/?agentId=agent-e2e-sec-preset"
        assert body["plain_ui_path"] == f"/?agentId=agent-e2e-sec-plain"
        assert body["explore_ui_path"] == f"/?agentId=agent-e2e-sec-explore"
        assert create_chat.await_count == 3

    def test_seed_security_preset_fixture_hidden_outside_local_mode(
        self, client: TestClient
    ) -> None:
        with patch(
            "app.api.chats.test_fixtures_security_preset.is_local_mode",
            return_value=False,
        ):
            resp = client.post("/api/v1/chats/test/seed-security-preset-fixture")
        assert resp.status_code == 404
