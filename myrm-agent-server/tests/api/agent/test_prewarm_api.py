"""Integration tests for chat turn prewarm endpoints."""

from collections.abc import Iterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with patch("app.core.security.auth.identity.is_loopback_ip", return_value=True):
        with TestClient(app) as test_client:
            yield test_client


@pytest.fixture(autouse=True)
def _reset_coordinator() -> Iterator[None]:
    from app.services.agent.execution_cache.prewarm.coordinator import (
        get_turn_prewarm_coordinator,
    )

    coordinator = get_turn_prewarm_coordinator()
    coordinator._inflight_acquire.clear()
    coordinator._inflight_brief.clear()
    coordinator._agent_ready_at.clear()
    yield
    coordinator._inflight_acquire.clear()
    coordinator._inflight_brief.clear()
    coordinator._agent_ready_at.clear()


class TestPrewarmEndpoint:
    def test_prewarm_fast_mode_skipped(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/agents/chats/c-prewarm-fast/prewarm",
            json={"actionMode": "fast"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["data"]["started"] is False
        assert body["data"]["reason"] == "skipped_mode"

    def test_prewarm_incognito_skipped(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/agents/chats/c-prewarm-incognito/prewarm",
            json={"incognitoMode": True},
        )
        body = resp.json()
        assert body["success"] is True
        assert body["data"]["started"] is False

    def test_prewarm_starts_warming(self, client: TestClient) -> None:
        mock_params = MagicMock()
        mock_params.chat_id = "c-prewarm-ok"
        with patch(
            "app.api.agents.general_agent.prewarm.resolve_prewarm_agent_params",
            new_callable=AsyncMock,
            return_value=mock_params,
        ), patch(
            "app.api.agents.general_agent.prewarm.get_turn_prewarm_coordinator",
        ) as mock_get_coordinator:
            coordinator = MagicMock()
            coordinator.ensure_warming = AsyncMock()
            mock_get_coordinator.return_value = coordinator

            resp = client.post(
                "/api/v1/agents/chats/c-prewarm-ok/prewarm",
                json={"agentId": "default", "actionMode": "agent"},
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["data"]["started"] is True
        assert body["data"]["chat_id"] == "c-prewarm-ok"
        coordinator.ensure_warming.assert_awaited_once()

    def test_cancel_prewarm(self, client: TestClient) -> None:
        with patch(
            "app.api.agents.general_agent.prewarm.get_turn_prewarm_coordinator",
        ) as mock_get_coordinator:
            coordinator = MagicMock()
            coordinator.cancel_scope = AsyncMock()
            mock_get_coordinator.return_value = coordinator

            resp = client.delete(
                "/api/v1/agents/chats/c-prewarm-cancel/prewarm?agent_id=default",
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["data"]["cancelled"] is True
        coordinator.cancel_scope.assert_awaited_once_with("c-prewarm-cancel", "default")
