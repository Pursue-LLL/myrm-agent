"""Unit tests for lazy session persistence gate."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.agent.stream_session.lazy_session_gate import (
    PendingSessionDraft,
    commit_lazy_session_barrier,
    is_active_generation_chunk,
)


def test_is_active_generation_chunk_string():
    assert is_active_generation_chunk("hello world") is True
    assert is_active_generation_chunk("   ") is False
    assert is_active_generation_chunk("") is False


def test_is_active_generation_chunk_events():
    # Passive events must return False
    assert is_active_generation_chunk({"type": "status", "data": "thinking"}) is False
    assert is_active_generation_chunk({"type": "routing", "data": "fast"}) is False
    assert is_active_generation_chunk({"type": "token_economics", "data": {}}) is False
    assert is_active_generation_chunk({"type": "warning", "data": "timeout"}) is False

    # Message event with real content
    assert is_active_generation_chunk({"type": "message", "data": "Hello!"}) is True
    assert is_active_generation_chunk({"type": "message", "data": {"content": "Hello!"}}) is True
    assert is_active_generation_chunk({"type": "message", "data": {"text": "Hello!"}}) is True
    assert is_active_generation_chunk({"type": "message", "data": ""}) is False
    assert is_active_generation_chunk({"type": "message", "data": "   "}) is False
    assert is_active_generation_chunk({"type": "message", "data": {"content": ""}}) is False

    # Reasoning event with real content
    assert is_active_generation_chunk({"type": "reasoning", "data": "Analyzing..."}) is True
    assert is_active_generation_chunk({"type": "reasoning", "data": {"text": "Step 1"}}) is True
    assert is_active_generation_chunk({"type": "reasoning", "data": "   "}) is False

    # Tool calls and HITL interactions
    assert is_active_generation_chunk({"type": "tool_call", "name": "bash"}) is True
    assert is_active_generation_chunk({"type": "action", "data": {}}) is True
    assert is_active_generation_chunk({"type": "clarification_required", "data": {}}) is True
    assert is_active_generation_chunk({"type": "approval_intercepted", "data": {}}) is True

    # Chunks using 'event' key instead of 'type'
    assert is_active_generation_chunk({"event": "message", "data": "Hello event!"}) is True
    assert is_active_generation_chunk({"event": "tool_call", "name": "bash"}) is True
    assert is_active_generation_chunk({"event": "status", "data": "thinking"}) is False


@pytest.mark.asyncio
async def test_pending_session_draft_idempotent_commit():
    draft = PendingSessionDraft(
        chat_id="chat-lazy-123",
        user_content="Write a script",
        sent_at=datetime.now(UTC),
        sent_timezone="UTC",
        message_id="msg-u1",
        action_mode="agent",
        agent_id="general",
    )
    assert draft.committed is False

    with patch("app.services.chat.chat_service.ChatService.ensure_chat_and_append_user_message", new_callable=AsyncMock) as mock_append:
        await draft.commit_if_pending()
        assert draft.committed is True
        mock_append.assert_awaited_once_with(
            chat_id="chat-lazy-123",
            content="Write a script",
            sent_at=draft.sent_at,
            sent_timezone="UTC",
            message_id="msg-u1",
            action_mode="agent",
            agent_id="general",
            ephemeral_subagents=None,
            extra_data=None,
            is_incognito=False,
            active_moa_preset_id=None,
            persist_moa_preset=False,
        )

        # Second call must be a no-op
        await draft.commit_if_pending()
        assert mock_append.await_count == 1


@pytest.mark.asyncio
async def test_commit_lazy_session_barrier():
    session = MagicMock()
    session.request = MagicMock()
    session.request.chat_id = "chat-lazy-456"

    # 1. No draft attached
    session.pending_session_draft = None
    with patch("app.services.agent.params.workspace_resolve.materialize_default_chat_workspace_dir", new_callable=AsyncMock) as mock_mat:
        await commit_lazy_session_barrier(session)
        mock_mat.assert_not_called()

    # 2. Draft attached and committed
    draft = PendingSessionDraft(
        chat_id="chat-lazy-456",
        user_content="Test query",
        sent_at=datetime.now(UTC),
        sent_timezone="UTC",
        message_id="msg-u2",
        action_mode="fast",
        agent_id="general",
    )
    session.pending_session_draft = draft

    with (
        patch("app.services.chat.chat_service.ChatService.ensure_chat_and_append_user_message", new_callable=AsyncMock) as mock_append,
        patch("app.services.agent.params.workspace_resolve.materialize_default_chat_workspace_dir", new_callable=AsyncMock) as mock_mat,
    ):
        await commit_lazy_session_barrier(session)
        assert draft.committed is True
        mock_append.assert_awaited_once()
        mock_mat.assert_awaited_once_with("chat-lazy-456")

        # Calling again does not re-commit or re-materialize
        await commit_lazy_session_barrier(session)
        assert mock_append.await_count == 1
        assert mock_mat.await_count == 1
