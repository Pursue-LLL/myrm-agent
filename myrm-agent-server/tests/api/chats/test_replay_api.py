"""Unit and integration tests for Session Replay and Determinism verification API."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="chats")


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_replay_session_not_found(client: TestClient) -> None:
    with patch(
        "app.services.chat.chat_service.ChatService.get_chat_metadata",
        new_callable=AsyncMock,
    ) as mock_get:
        mock_get.return_value = None
        resp = client.post("/api/v1/chats/non-existent-chat-id/replay", json={"mode": "live"})
        assert resp.status_code == 404


def test_replay_session_empty_messages(client: TestClient) -> None:
    mock_chat = SimpleNamespace(id="chat-123", title="Test Chat")
    with (
        patch(
            "app.services.chat.chat_service.ChatService.get_chat_metadata",
            new_callable=AsyncMock,
        ) as mock_get,
        patch(
            "app.services.chat.chat_service.ChatService.get_messages_paginated",
            new_callable=AsyncMock,
        ) as mock_msgs,
    ):
        mock_get.return_value = mock_chat
        mock_msgs.return_value = ([], 0)
        resp = client.post("/api/v1/chats/chat-123/replay", json={"mode": "live"})
        assert resp.status_code == 400


def test_replay_session_success(client: TestClient) -> None:
    mock_chat = SimpleNamespace(id="chat-123", title="Test Chat")
    mock_msg = SimpleNamespace(
        id="msg-1",
        role="assistant",
        extra_data={
            "tasks_steps": [
                {
                    "tool_name": "read_file",
                    "arguments": {"path": "main.py"},
                    "result": "OK",
                    "duration_ms": 100,
                }
            ]
        },
        content="Read completed",
    )

    with (
        patch(
            "app.services.chat.chat_service.ChatService.get_chat_metadata",
            new_callable=AsyncMock,
        ) as mock_get,
        patch(
            "app.services.chat.chat_service.ChatService.get_messages_paginated",
            new_callable=AsyncMock,
        ) as mock_msgs,
    ):
        mock_get.return_value = mock_chat
        mock_msgs.return_value = ([mock_msg], 1)
        resp = client.post("/api/v1/chats/chat-123/replay", json={"mode": "live"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["session_id"] == "chat-123"
        assert data["determinism_score"] == 1.0
        assert data["verdict"] == "DETERMINISTIC"
        assert data["original_tool_count"] == 1
        assert data["replayed_tool_count"] == 1
        assert len(data["replayed_steps"]) == 1
        assert data["replayed_steps"][0]["tool_name"] == "read_file"
