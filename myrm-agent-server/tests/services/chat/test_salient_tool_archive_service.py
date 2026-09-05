"""Unit tests for SalientToolArchiveService."""

from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.messages import ToolMessage

from app.services.chat.salient_tool_archive_service import SalientToolArchiveService


@pytest.mark.asyncio
async def test_archive_salient_tools_success() -> None:
    mock_db = AsyncMock()
    service = SalientToolArchiveService()

    msg = ToolMessage(
        content="FAILED: assertion 400 == 200\nexit code: 1",
        tool_call_id="call_mock_456",
        name="bash",
        status="error",
    )

    with patch(
        "app.services.chat.salient_tool_archive_service.ConversationRecallIndexService.append_salient_tool_evidence",
        new_callable=AsyncMock,
    ) as mock_append:
        archived = await service.archive_salient_tools(
            mock_db,
            chat_id="chat_test_123",
            messages=[msg],
        )

        assert len(archived) == 1
        assert archived[0].tool_name == "bash"
        assert archived[0].is_error is True
        mock_append.assert_awaited_once()


@pytest.mark.asyncio
async def test_archive_salient_tools_no_candidates() -> None:
    mock_db = AsyncMock()
    service = SalientToolArchiveService()

    benign_msg = ToolMessage(
        content="Everything succeeded cleanly",
        tool_call_id="call_clean",
        name="reader",
    )

    with patch(
        "app.services.chat.salient_tool_archive_service.ConversationRecallIndexService.append_salient_tool_evidence",
        new_callable=AsyncMock,
    ) as mock_append:
        archived = await service.archive_salient_tools(
            mock_db,
            chat_id="chat_test_123",
            messages=[benign_msg],
        )

        assert len(archived) == 0
        mock_append.assert_not_awaited()
