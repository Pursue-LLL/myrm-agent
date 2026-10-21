"""Unit tests for Cross-Session Trajectory API."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="chats")


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_get_session_trajectory_not_found(client: TestClient) -> None:
    with patch(
        "app.services.chat.chat_service.ChatService.get_chat_metadata",
        new_callable=AsyncMock,
    ) as mock_meta:
        mock_meta.return_value = None
        resp = client.get("/api/v1/chats/non-existent-session-id/trajectory")
        assert resp.status_code == 404


def test_get_session_trajectory_success(client: TestClient) -> None:
    from types import SimpleNamespace

    mock_chat = SimpleNamespace(title="Test Session", name="Test Session")
    mock_msg1 = SimpleNamespace(
        id="msg-1",
        role="user",
        content="Fetch data from url",
        extra_data={},
        created_at="2026-08-25T12:00:00Z",
    )
    mock_msg2 = SimpleNamespace(
        id="msg-2",
        role="assistant",
        content="Here is the data",
        extra_data={
            "tasks_steps": [
                {
                    "tool_name": "web_fetch",
                    "arguments": {"url": "https://example.com"},
                    "result": "OK 200",
                    "duration_ms": 150.0,
                    "tokens": 45,
                }
            ],
            "token_usage": 500,
        },
        created_at="2026-08-25T12:00:02Z",
    )

    with (
        patch(
            "app.services.chat.chat_service.ChatService.get_chat_metadata",
            new_callable=AsyncMock,
        ) as mock_meta,
        patch(
            "app.services.chat.chat_service.ChatService.get_messages_paginated",
            new_callable=AsyncMock,
        ) as mock_msgs,
    ):
        mock_meta.return_value = mock_chat
        mock_msgs.return_value = ([mock_msg1, mock_msg2], False)

        resp = client.get("/api/v1/chats/session-123/trajectory")
        assert resp.status_code == 200
        data = resp.json()
        assert data["session_id"] == "session-123"
        assert data["title"] == "Test Session"
        assert data["total_turns"] == 1
        assert data["total_tool_calls"] == 1
        assert len(data["turns"][0]["steps"]) == 1
        assert data["turns"][0]["steps"][0]["tool_name"] == "web_fetch"
