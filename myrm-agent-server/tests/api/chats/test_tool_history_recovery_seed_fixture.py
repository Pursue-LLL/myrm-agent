"""Integration test for tool_history recovery Chrome E2E seed fixture."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="chats")


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_seed_tool_history_recovery_fixture_persists_progress_steps(
    client: TestClient,
) -> None:
    fake_agent = MagicMock()
    fake_agent.id = "agent-e2e-tool-history"
    fake_agent.display_name = "Tool History E2E Agent"
    captured_extra: dict[str, object] = {}

    async def _append_message(
        chat_id: str,
        role: str,
        content: str,
        created_at: object,
        timezone: str,
        *,
        message_id: str | None = None,
        extra_data: dict[str, object] | None = None,
        **kwargs: object,
    ) -> None:
        del chat_id, role, content, created_at, timezone, message_id, kwargs
        if extra_data is not None:
            captured_extra.update(extra_data)

    with (
        patch(
            "app.api.chats.test_fixtures_tool_history_recovery.is_local_mode",
            return_value=True,
        ),
        patch(
            "app.api.chats.test_fixtures_tool_history_recovery.AgentService.get_agent_list",
            new_callable=AsyncMock,
            return_value=([fake_agent], 1),
        ),
        patch(
            "app.api.chats.test_fixtures_tool_history_recovery.ChatService.create_or_update_chat",
            new_callable=AsyncMock,
        ),
        patch(
            "app.api.chats.test_fixtures_tool_history_recovery.ChatService.append_message",
            side_effect=_append_message,
        ),
    ):
        response = client.post("/api/v1/chats/test/seed-tool-history-recovery-fixture")

    assert response.status_code == 200, response.text
    payload = response.json()
    chat_id = str(payload.get("chat_id") or "")
    assert chat_id.startswith("e2etoolhist")

    steps = captured_extra.get("progressSteps") or []
    assert isinstance(steps, list)
    step_keys = {str(step.get("step_key") or "") for step in steps if isinstance(step, dict)}
    assert "tool_history_recovery" in step_keys
