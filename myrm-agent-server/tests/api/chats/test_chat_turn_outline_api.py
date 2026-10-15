"""API tests for `GET /chats/{chat_id}/outline` (turn outline projection for the navigation rail)."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.database.dto import TurnOutlineItem
from tests.support.minimal_app import build_minimal_app

_GET_METADATA = "app.services.chat.chat_service.ChatService.get_chat_metadata"
_GET_OUTLINE = "app.services.chat.turn_outline_service.TurnOutlineProjectionService.get_chat_turn_outline"

app = build_minimal_app("chats")


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_outline_returns_projected_turns(client: TestClient) -> None:
    created_at = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    turns = [
        TurnOutlineItem(
            turn_index=1,
            user_message_id="u1",
            assistant_message_id="a1",
            prompt_preview="hello",
            reply_preview="hi there",
            created_at=created_at,
            message_count=2,
        )
    ]
    with (
        patch(_GET_METADATA, new_callable=AsyncMock, return_value=object()),
        patch(_GET_OUTLINE, new_callable=AsyncMock, return_value=turns),
    ):
        resp = client.get("/api/v1/chats/chat-1/outline")

    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["data"] == [
        {
            "turn_index": 1,
            "user_message_id": "u1",
            "assistant_message_id": "a1",
            "prompt_preview": "hello",
            "reply_preview": "hi there",
            "created_at": "2026-01-02T03:04:05Z",
            "message_count": 2,
        }
    ]


def test_outline_unknown_chat_is_404(client: TestClient) -> None:
    with patch(_GET_METADATA, new_callable=AsyncMock, return_value=None):
        resp = client.get("/api/v1/chats/missing/outline")

    assert resp.status_code == 404
