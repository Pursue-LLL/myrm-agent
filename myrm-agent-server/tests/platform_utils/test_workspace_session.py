"""Tests for chat workspace session id normalization."""

from __future__ import annotations

from app.platform_utils.workspace_session import to_rest_chat_id, to_workspace_session_id


def test_to_workspace_session_id_adds_prefix() -> None:
    assert to_workspace_session_id("abc-123") == "chat_abc-123"


def test_to_workspace_session_id_idempotent() -> None:
    assert to_workspace_session_id("chat_abc-123") == "chat_abc-123"


def test_to_workspace_session_id_strips_whitespace() -> None:
    assert to_workspace_session_id("  abc-123  ") == "chat_abc-123"


def test_to_rest_chat_id_strips_prefix() -> None:
    assert to_rest_chat_id("chat_e2e-bgshell-abc") == "e2e-bgshell-abc"


def test_to_rest_chat_id_idempotent_on_plain_chat_id() -> None:
    assert to_rest_chat_id("e2e-bgshell-abc") == "e2e-bgshell-abc"
