"""Integration test for memory lifecycle Chrome E2E seed fixture."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="chats")


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_seed_memory_lifecycle_fixture_returns_chat_and_message_ids(
    client: TestClient,
) -> None:
    fake_agent = MagicMock()
    fake_agent.id = "agent-e2e-memory-lifecycle"
    ledger_calls: list[dict[str, object]] = []

    async def _record_event(**kwargs: object) -> MagicMock:
        ledger_calls.append(dict(kwargs))
        return MagicMock()

    mock_ledger = MagicMock()
    mock_ledger.record_event = AsyncMock(side_effect=_record_event)

    mock_session = MagicMock()
    mock_session.__aenter__ = AsyncMock(return_value=MagicMock())
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with (
        patch(
            "app.api.chats.test_fixtures_memory_lifecycle.is_local_mode",
            return_value=True,
        ),
        patch(
            "app.api.chats.test_fixtures_memory_lifecycle.AgentService.get_agent_list",
            new_callable=AsyncMock,
            return_value=([fake_agent], 1),
        ),
        patch(
            "app.api.chats.test_fixtures_memory_lifecycle.ChatService.create_or_update_chat",
            new_callable=AsyncMock,
        ),
        patch(
            "app.api.chats.test_fixtures_memory_lifecycle.ChatService.append_message",
            new_callable=AsyncMock,
        ),
        patch(
            "app.api.chats.test_fixtures_memory_lifecycle.get_session",
            return_value=mock_session,
        ),
        patch(
            "app.api.chats.test_fixtures_memory_lifecycle.MemoryOperationLedgerService",
            return_value=mock_ledger,
        ),
    ):
        response = client.post("/api/v1/chats/test/seed-memory-lifecycle-fixture")

    assert response.status_code == 200, response.text
    payload = response.json()
    chat_id = str(payload.get("chat_id") or "")
    message_id = str(payload.get("message_id") or "")
    assert chat_id.startswith("e2ememlife")
    assert message_id
    assert payload.get("ui_path") == f"/{chat_id}"

    assert len(ledger_calls) == 2
    write_call = ledger_calls[0]
    extract_call = ledger_calls[1]
    assert write_call.get("status") is not None
    assert str(write_call.get("summary") or "").startswith("Memory write ok")
    assert extract_call.get("status") is not None
    assert "failed" in str(extract_call.get("summary") or "").lower()
