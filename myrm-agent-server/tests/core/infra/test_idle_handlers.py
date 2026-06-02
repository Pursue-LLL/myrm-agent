"""Tests for server-level idle task handlers.

Tests context_compact_impl and register_all_idle_handlers.
"""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
class TestContextCompactImpl:
    """Tests for the context_compact_impl idle handler."""

    async def test_compaction_success(self) -> None:
        mock_result = MagicMock()
        mock_result.compacted = True
        mock_result.tokens_saved = 5000
        mock_result.message_count = 20
        mock_result.reason = None

        mock_compact_chat = AsyncMock(return_value=mock_result)
        mock_session = AsyncMock()

        @asynccontextmanager
        async def fake_get_session():
            yield mock_session

        with patch("app.database.connection.get_session", fake_get_session), \
             patch("app.services.chat.compact_service.compact_chat", mock_compact_chat):
            from app.core.infra.idle_handlers import context_compact_impl

            result = await context_compact_impl("chat_123", "session_1")

        assert result["compacted"] is True
        assert result["tokens_saved"] == 5000
        assert result["message_count"] == 20
        assert result["reason"] == ""
        mock_compact_chat.assert_awaited_once_with(mock_session, "chat_123")

    async def test_compaction_skipped(self) -> None:
        mock_result = MagicMock()
        mock_result.compacted = False
        mock_result.tokens_saved = 0
        mock_result.message_count = 5
        mock_result.reason = "too_few_messages (5 < 10)"

        mock_compact_chat = AsyncMock(return_value=mock_result)
        mock_session = AsyncMock()

        @asynccontextmanager
        async def fake_get_session():
            yield mock_session

        with patch("app.database.connection.get_session", fake_get_session), \
             patch("app.services.chat.compact_service.compact_chat", mock_compact_chat):
            from app.core.infra.idle_handlers import context_compact_impl

            result = await context_compact_impl("chat_short", "session_2")

        assert result["compacted"] is False
        assert result["tokens_saved"] == 0
        assert "too_few_messages" in result["reason"]


class TestRegisterAllIdleHandlers:
    """Tests for handler registration."""

    def test_registers_handlers(self) -> None:
        with patch("app.core.infra.idle_handlers.register_idle_task_handler") as mock_register:
            from app.core.infra.idle_handlers import register_all_idle_handlers

            register_all_idle_handlers()

            calls = {c.args[0] for c in mock_register.call_args_list}
            assert "wiki_maintenance" in calls
            assert "_context_compact_impl" in calls
