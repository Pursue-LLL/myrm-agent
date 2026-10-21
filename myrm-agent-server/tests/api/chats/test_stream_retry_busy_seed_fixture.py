"""HTTP tests for stream-retry-busy seed fixture."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="chats")


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_busy_fixture_query_is_not_risk_blocked() -> None:
    """Fixture query must not hit stream risk gate (e.g. avoid 'contract' keyword)."""
    from app.api.chats.test_fixtures.stream_retry_busy import _BUSY_QUERY_TEXT
    from app.services.agent.stream_session.risk_gate import check_stream_risk

    blocked = await check_stream_risk(_BUSY_QUERY_TEXT, "e2estreamretryfixture")
    assert blocked is None


@pytest.mark.integration
def test_seed_and_release_stream_retry_busy_fixture(client: TestClient) -> None:
    fake_agent = MagicMock()
    fake_agent.id = "agent-e2e-stream-retry"

    with (
        patch(
            "app.api.chats.test_fixtures.stream_retry_busy.is_local_mode",
            return_value=True,
        ),
        patch(
            "app.api.chats.test_fixtures.stream_retry_busy.AgentService.get_agent_list",
            new_callable=AsyncMock,
            return_value=([fake_agent], 1),
        ),
        patch(
            "app.api.chats.test_fixtures.stream_retry_busy.ChatService.create_or_update_chat",
            new_callable=AsyncMock,
        ),
        patch(
            "app.api.chats.test_fixtures.stream_retry_busy.ChatService.ensure_chat_and_append_user_message",
            new_callable=AsyncMock,
        ),
        patch(
            "app.api.chats.test_fixtures.stream_retry_busy.get_agent_gateway",
        ) as gateway_factory,
    ):
        gateway = MagicMock()
        gateway_factory.return_value = gateway
        seed_resp = client.post("/api/v1/chats/test/seed-stream-retry-busy-fixture")
        assert seed_resp.status_code == 200
        payload = seed_resp.json()
        chat_id = str(payload.get("chat_id") or "")
        assert chat_id.startswith("e2estreamretry")
        gateway.reserve_session.assert_called_once()

    with patch(
        "app.api.chats.test_fixtures.stream_retry_busy.is_local_mode",
        return_value=True,
    ):
        release_resp = client.post(
            "/api/v1/chats/test/release-stream-retry-busy-fixture",
            params={"chat_id": "e2estreamretrydeadbeef"},
        )
        assert release_resp.status_code == 200
        assert release_resp.json().get("released") is True
