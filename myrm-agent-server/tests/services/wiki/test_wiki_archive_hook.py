"""Tests for wiki SessionNotes archive hook."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.wiki.wiki_archive_hook import archive_session_notes_to_wiki


@pytest.mark.asyncio
async def test_archive_session_notes_success() -> None:
    mock_llm = MagicMock()
    mock_archiver = MagicMock()
    mock_archiver.archive_memory = AsyncMock(return_value=True)
    notes_json = '{"_meta":{"last_updated_message_idx":8},"task_spec":"build wiki"}'

    with patch(
        "app.services.wiki.wiki_archive_hook.get_wiki_archiver",
        return_value=mock_archiver,
    ):
        await archive_session_notes_to_wiki("chat-1", notes_json, llm=mock_llm)

    mock_archiver.archive_memory.assert_awaited_once_with(
        notes_json,
        conversation_turns=8,
        chat_id="chat-1",
    )


@pytest.mark.asyncio
async def test_archive_falls_back_to_message_count() -> None:
    mock_llm = MagicMock()
    mock_archiver = MagicMock()
    mock_archiver.archive_memory = AsyncMock(return_value=False)
    notes_json = '{"task_spec":"no meta block"}'

    with (
        patch(
            "app.services.wiki.wiki_archive_hook.get_wiki_archiver",
            return_value=mock_archiver,
        ),
        patch(
            "app.services.wiki.wiki_archive_hook.ChatService.count_messages",
            new_callable=AsyncMock,
            return_value=15,
        ) as mock_count,
    ):
        await archive_session_notes_to_wiki("chat-2", notes_json, llm=mock_llm)

    mock_count.assert_awaited_once_with("chat-2")
    mock_archiver.archive_memory.assert_awaited_once_with(
        notes_json,
        conversation_turns=15,
        chat_id="chat-2",
    )


@pytest.mark.asyncio
async def test_archive_swallows_errors() -> None:
    mock_llm = MagicMock()

    with patch(
        "app.services.wiki.wiki_archive_hook.get_wiki_archiver",
        side_effect=RuntimeError("vault unavailable"),
    ):
        await archive_session_notes_to_wiki("chat-3", "{}", llm=mock_llm)
