"""Unit tests for the salient tool segment header written by ConversationRecallRepository."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from app.database.repositories.conversation_recall.repo import (
    ConversationRecallRepository,
)


async def _persisted_segment(command: str, exit_code: int | None) -> str:
    db = AsyncMock()
    await ConversationRecallRepository.append_salient_tool_segment(
        db,
        chat_id="chat-1",
        message_id="msg-1",
        tool_name="bash",
        command=command,
        exit_code=exit_code,
        snippet="boom",
        sent_at=datetime(2026, 10, 12, tzinfo=timezone.utc),
    )
    segment_params = db.execute.await_args_list[-1].args[1]
    assert segment_params["role"] == "tool"
    return segment_params["content"]


@pytest.mark.asyncio
async def test_multiline_command_keeps_header_and_exit_code_on_first_line() -> None:
    content = await _persisted_segment("cat > run.sh <<EOF\n  echo hi\nEOF\nbash run.sh", exit_code=137)

    header, _, output = content.partition("\n")
    assert header == "Tool[bash] cmd=cat > run.sh <<EOF echo hi EOF bash run.sh exit=137"
    assert output == "boom"


@pytest.mark.asyncio
async def test_header_omits_absent_command_and_exit_code() -> None:
    content = await _persisted_segment("", exit_code=None)

    assert content == "Tool[bash]\nboom"
