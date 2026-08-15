"""Integration test for guardrail bash Chrome E2E seed fixture."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="chats")


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.mark.parametrize("variant", ["direct_import", "pipe_stdin", "python_m"])
def test_seed_guardrail_bash_fixture_persists_guardrail_step(
    client: TestClient,
    variant: str,
) -> None:
    fake_agent = MagicMock()
    fake_agent.id = "agent-e2e-guardrail-bash"
    fake_agent.display_name = "Guardrail Bash E2E Agent"
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
            "app.api.chats.test_fixtures.guardrail_bash.is_local_mode",
            return_value=True,
        ),
        patch(
            "app.api.chats.test_fixtures.guardrail_bash.AgentService.get_agent_list",
            new_callable=AsyncMock,
            return_value=([fake_agent], 1),
        ),
        patch(
            "app.api.chats.test_fixtures.guardrail_bash.ChatService.create_or_update_chat",
            new_callable=AsyncMock,
        ),
        patch(
            "app.api.chats.test_fixtures.guardrail_bash.ChatService.append_message",
            side_effect=_append_message,
        ),
    ):
        response = client.post(
            f"/api/v1/chats/test/seed-guardrail-bash-fixture?variant={variant}",
        )

    assert response.status_code == 200, response.text
    payload = response.json()
    chat_id = str(payload.get("chat_id") or "")
    assert chat_id.startswith("e2eguard")
    assert payload.get("variant") == variant

    steps = captured_extra.get("progressSteps") or []
    assert isinstance(steps, list)
    assert any(
        isinstance(step, dict)
        and step.get("step_key") == "bash_code_execute_tool"
        and step.get("error_category") == "guardrail_blocked"
        for step in steps
    )


def test_seed_guardrail_bash_fixture_rejects_unknown_variant(client: TestClient) -> None:
    with patch(
        "app.api.chats.test_fixtures.guardrail_bash.is_local_mode",
        return_value=True,
    ):
        response = client.post(
            "/api/v1/chats/test/seed-guardrail-bash-fixture?variant=unknown",
        )
    assert response.status_code == 400
