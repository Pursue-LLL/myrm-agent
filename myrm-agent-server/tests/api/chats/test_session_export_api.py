"""API tests for the interactive HTML export, the credential preview and the share link.

[INPUT]
- fastapi.FastAPI, starlette.testclient.TestClient
- app.api.chats.session_export_router
- app.services.chat.chat_service.ChatService (patched stand-in for the chat store)

[OUTPUT]
- Pytest cases: the export and the preview read the stored conversation, an unknown or unreadable
  chat is an error instead of a plausible-looking document, the preview predicts what the export scrubs.

[POS]
tests/api/chats/test_session_export_api.py: Test suite for the session export endpoints.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api.chats.session_export_router import router as session_export_router
from app.database.dto import ChatDTO, MessageDTO

_NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
_GET_METADATA = "app.services.chat.chat_service.ChatService.get_chat_metadata"
_GET_MESSAGES = "app.services.chat.chat_service.ChatService.get_all_messages"
_API_KEY = "sk-abcdef1234567890abcdef123456"

_OPTIONS = {"include_thinking": True, "include_tool_calls": True, "enable_redaction": True, "theme": "system"}


def _chat(chat_id: str, title: str = "Planning notes") -> ChatDTO:
    return ChatDTO(id=chat_id, title=title, created_at=_NOW, updated_at=_NOW)


def _message(index: int, role: str, content: str) -> MessageDTO:
    return MessageDTO(
        id=f"m{index}",
        chat_id="chat-1",
        role=role,
        content=content,
        sent_at=_NOW,
        sent_timezone="UTC",
        created_at=_NOW,
    )


@pytest.fixture
def export_app() -> FastAPI:
    app = FastAPI()
    app.include_router(session_export_router, prefix="/api/v1")
    return app


@pytest.fixture
def export_client(export_app: FastAPI) -> TestClient:
    return TestClient(export_app)


@pytest.fixture
def stored_chat() -> Iterator[list[MessageDTO]]:
    """A chat store holding one conversation; tests append the messages they need."""
    messages: list[MessageDTO] = []
    with (
        patch(_GET_METADATA, new_callable=AsyncMock, return_value=_chat("chat-1")),
        patch(_GET_MESSAGES, new_callable=AsyncMock, return_value=messages),
    ):
        yield messages


@pytest.fixture
def unknown_chat() -> Iterator[None]:
    with patch(_GET_METADATA, new_callable=AsyncMock, return_value=None):
        yield


def test_export_renders_the_stored_conversation(export_client: TestClient, stored_chat: list[MessageDTO]) -> None:
    stored_chat.extend([_message(1, "user", "Why is the nightly job slow?"), _message(2, "assistant", "The index is missing.")])

    res = export_client.post("/api/v1/chats/chat-1/export/interactive-html", json=_OPTIONS)

    assert res.status_code == 200
    data = res.json()
    assert data["chat_id"] == "chat-1"
    assert data["title"] == "Planning notes"
    assert data["total_messages"] == 2
    assert data["file_name"].startswith("myrm-session-") and data["file_name"].endswith(".html")
    assert data["size_bytes"] > 0
    html = data["html_content"]
    assert "Why is the nightly job slow?" in html
    assert "The index is missing." in html
    assert 'data-theme="system"' in html
    assert '<script src="http' not in html
    assert '<link rel="stylesheet" href="http' not in html


def test_export_of_an_unknown_chat_is_not_found_instead_of_a_made_up_conversation(
    export_client: TestClient, unknown_chat: None
) -> None:
    res = export_client.post("/api/v1/chats/no-such-chat/export/interactive-html", json=_OPTIONS)

    assert res.status_code == 404
    assert "html_content" not in res.text


def test_export_of_a_chat_that_cannot_be_read_fails_instead_of_returning_a_document(export_app: FastAPI) -> None:
    client = TestClient(export_app, raise_server_exceptions=False)
    with patch(_GET_METADATA, new_callable=AsyncMock, side_effect=RuntimeError("database offline")):
        res = client.post("/api/v1/chats/chat-1/export/interactive-html", json=_OPTIONS)

    assert res.status_code == 500
    assert "html_content" not in res.text


def test_export_scrubs_credentials_in_the_stored_messages(export_client: TestClient, stored_chat: list[MessageDTO]) -> None:
    stored_chat.append(_message(1, "user", f"My key is {_API_KEY}"))

    res = export_client.post("/api/v1/chats/chat-1/export/interactive-html", json=_OPTIONS)

    data = res.json()
    assert _API_KEY not in data["html_content"]
    assert data["redaction_summary"]["total_redacted"] == 1


def test_preview_scans_the_conversation_content_not_its_title(export_client: TestClient, stored_chat: list[MessageDTO]) -> None:
    stored_chat.extend([_message(1, "user", f"Use {_API_KEY} for staging"), _message(2, "assistant", "Noted.")])

    res = export_client.post("/api/v1/chats/chat-1/export/redact-preview")

    assert res.status_code == 200
    data = res.json()
    assert data["has_secrets"] is True
    assert data["total_redacted"] == 1
    assert [d["pattern_type"] for d in data["details"]] == ["api_key"]


def test_preview_of_a_conversation_without_credentials_is_clean(export_client: TestClient, stored_chat: list[MessageDTO]) -> None:
    stored_chat.append(_message(1, "user", "Nothing sensitive here."))

    res = export_client.post("/api/v1/chats/chat-1/export/redact-preview")

    assert res.status_code == 200
    assert res.json() == {"total_redacted": 0, "has_secrets": False, "details": []}


def test_preview_merges_one_pattern_found_in_several_messages_into_one_entry(
    export_client: TestClient, stored_chat: list[MessageDTO]
) -> None:
    stored_chat.extend([_message(1, "user", f"first {_API_KEY}"), _message(2, "user", f"second {_API_KEY}")])

    data = export_client.post("/api/v1/chats/chat-1/export/redact-preview").json()

    assert data["total_redacted"] == 2
    assert [(d["pattern_type"], d["count"]) for d in data["details"]] == [("api_key", 2)]


def test_preview_predicts_what_the_export_scrubs(export_client: TestClient, stored_chat: list[MessageDTO]) -> None:
    stored_chat.extend(
        [
            _message(1, "user", f"key {_API_KEY} on 192.168.1.150"),
            _message(2, "assistant", "password: 'my_top_secret_token'"),
        ]
    )

    preview = export_client.post("/api/v1/chats/chat-1/export/redact-preview").json()
    exported = export_client.post("/api/v1/chats/chat-1/export/interactive-html", json=_OPTIONS).json()

    assert preview["total_redacted"] == 3
    assert exported["redaction_summary"] == preview


def test_preview_of_an_unknown_chat_is_not_found(export_client: TestClient, unknown_chat: None) -> None:
    res = export_client.post("/api/v1/chats/no-such-chat/export/redact-preview")

    assert res.status_code == 404


def test_create_chat_share_link_api(export_client: TestClient) -> None:
    """POST /api/v1/chats/{chat_id}/export/share-link produces a valid HMAC share URL."""
    payload = {
        "ttl_seconds": 3600,
        "password": None,
    }
    res = export_client.post("/api/v1/chats/chat-share-999/export/share-link", json=payload)
    assert res.status_code == 200
    data = res.json()

    assert data["chat_id"] == "chat-share-999"
    assert "/share/" in data["share_url"]
    assert len(data["share_token"]) > 10
    assert data["expires_at_unix"] > 0
    assert data["is_password_protected"] is False
