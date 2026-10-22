"""Unit tests for Interactive Single-File HTML Export & Share Link API endpoints.

[INPUT]
- fastapi.FastAPI, starlette.testclient.TestClient
- app.api.chats.session_export_router

[OUTPUT]
- Pytest test cases covering standalone HTML compilation, secret scrubbing, and HMAC share links.

[POS]
tests/api/chats/test_session_export_api.py: Comprehensive test suite for session export endpoints.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api.chats.session_export_router import router as session_export_router


@pytest.fixture
def export_client() -> TestClient:
    """Provide isolated TestClient fixture mounting session_export_router."""
    app = FastAPI()
    app.include_router(session_export_router, prefix="/api/v1")
    return TestClient(app)


def test_export_chat_interactive_html(export_client: TestClient) -> None:
    """Verify POST /api/v1/chats/{chat_id}/export/interactive-html generates self-contained bundle."""
    payload = {
        "include_thinking": True,
        "include_tool_calls": True,
        "enable_redaction": True,
        "theme": "system",
    }
    res = export_client.post("/api/v1/chats/chat-exp-001/export/interactive-html", json=payload)
    assert res.status_code == 200
    data = res.json()

    assert data["chat_id"] == "chat-exp-001"
    assert data["file_name"].startswith("myrm-session-")
    assert data["file_name"].endswith(".html")
    assert data["size_bytes"] > 0
    assert data["total_messages"] >= 2

    html = data["html_content"]
    assert "<!DOCTYPE html>" in html
    assert "data-theme=\"system\"" in html
    assert "thinking-drawer" in html
    assert "tools-drawer" in html
    assert "copy-btn" in html
    # Ensure zero external network scripts or styles
    assert "<script src=\"http" not in html
    assert "<link rel=\"stylesheet\" href=\"http" not in html


def test_export_chat_interactive_html_with_redaction(export_client: TestClient) -> None:
    """Verify secret credentials like API keys and private IPs are scrubbed upon export."""
    payload = {
        "include_thinking": True,
        "include_tool_calls": True,
        "enable_redaction": True,
        "theme": "dark",
    }
    res = export_client.post("/api/v1/chats/chat-exp-secret/export/interactive-html", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert "redaction_summary" in data


def test_preview_secret_redaction_api(export_client: TestClient) -> None:
    """Verify POST /api/v1/chats/export/redact-preview detects high-risk credentials."""
    sample_text = (
        "Here is my OpenAI key sk-abcdef1234567890abcdef123456 "
        "and internal cluster IP 192.168.1.150 and secret_key: 'my_top_secret_token'"
    )
    res = export_client.post("/api/v1/chats/export/redact-preview", json={"text": sample_text})
    assert res.status_code == 200
    data = res.json()

    assert data["has_secrets"] is True
    assert data["total_redacted"] >= 2
    types = {d["pattern_type"] for d in data["details"]}
    assert "api_key" in types or "internal_ip" in types


def test_create_chat_share_link_api(export_client: TestClient) -> None:
    """Verify POST /api/v1/chats/{chat_id}/export/share-link produces valid HMAC share URL."""
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
