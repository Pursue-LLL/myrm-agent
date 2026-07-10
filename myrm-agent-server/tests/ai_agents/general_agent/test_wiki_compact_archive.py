"""Tests for wiki archive trigger on compaction persist wrapper."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import app.services.wiki.wiki_archive_hook as wiki_archive_hook_module
from app.ai_agents.general_agent.callbacks import make_summary_persist_with_wiki_archive

async def test_wiki_archive_runs_after_compaction_persist() -> None:
    mock_llm = MagicMock()
    notes_json = '{"_meta":{"last_updated_message_idx":12},"task_spec":"x"}'

    async def _load_notes() -> str:
        return notes_json

    pending_coros: list[object] = []

    def _capture_background_task(coro: object) -> MagicMock:
        pending_coros.append(coro)
        return MagicMock()

    with (
        patch(
            "app.ai_agents.general_agent.callbacks.get_persist_compaction",
            return_value=AsyncMock(),
        ) as mock_get_persist,
        patch(
            "app.ai_agents.general_agent.callbacks.make_notes_load",
            return_value=_load_notes,
        ),
        patch.object(
            wiki_archive_hook_module,
            "archive_session_notes_to_wiki",
            new_callable=AsyncMock,
        ) as mock_archive,
        patch("asyncio.create_task", side_effect=_capture_background_task),
        patch("myrm_agent_harness.api.track_background_task"),
    ):
        base = AsyncMock()
        mock_get_persist.return_value = base
        callback = make_summary_persist_with_wiki_archive(enable_wiki=True, wiki_archive_llm=mock_llm)
        await callback("chat-1", object(), "msg-1", 1000)
        for pending in pending_coros:
            await pending  # type: ignore[misc]
        base.assert_awaited_once()

    mock_archive.assert_awaited()


@pytest.mark.asyncio
async def test_wiki_archive_skipped_when_disabled() -> None:
    with (
        patch(
            "app.ai_agents.general_agent.callbacks.get_persist_compaction",
            return_value=AsyncMock(),
        ) as mock_get_persist,
        patch.object(
            wiki_archive_hook_module,
            "archive_session_notes_to_wiki",
            new_callable=AsyncMock,
        ) as mock_archive,
    ):
        base = AsyncMock()
        mock_get_persist.return_value = base
        callback = make_summary_persist_with_wiki_archive(enable_wiki=False, wiki_archive_llm=None)
        await callback("chat-1", object(), "msg-1", 1000)
        base.assert_awaited_once()
        mock_archive.assert_not_awaited()
