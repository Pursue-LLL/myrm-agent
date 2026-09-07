"""Unit tests for TurnOutlineProjectionService in myrm-agent-server.

Tests folding raw conversation messages into compact TurnOutlineItem projections.
"""

from __future__ import annotations

import datetime
from app.database.dto import MessageDTO, TurnOutlineItem
from app.services.chat.turn_outline_service import (
    TurnOutlineProjectionService,
    _sanitize_preview_text,
)


def test_sanitize_preview_text() -> None:
    raw = "   This is a   long message\nwith newlines\n\nand   tabs.   "
    cleaned = _sanitize_preview_text(raw, max_chars=20)
    assert len(cleaned) <= 23  # with '...'
    assert "\n" not in cleaned
    assert "This is a long..." in cleaned


def test_build_outline_empty() -> None:
    outlines = TurnOutlineProjectionService.build_outline_from_messages([])
    assert outlines == []


def test_build_outline_single_turn() -> None:
    now = datetime.datetime.now(datetime.timezone.utc)
    messages = [
        MessageDTO(
            id="msg-1",
            chat_id="chat-123",
            role="user",
            content="Hello world, please help me analyze this architecture document.",
            created_at=now,
        ),
        MessageDTO(
            id="msg-2",
            chat_id="chat-123",
            role="assistant",
            content="<think>\nAnalyzing the architecture...\n</think>\nSure! Here is the architecture analysis.",
            created_at=now,
        ),
    ]

    outlines = TurnOutlineProjectionService.build_outline_from_messages(messages)
    assert len(outlines) == 1
    item = outlines[0]
    assert item.turn_index == 1
    assert item.user_message_id == "msg-1"
    assert item.assistant_message_id == "msg-2"
    assert "Hello world" in item.prompt_preview
    assert item.reply_preview is not None
    assert "<think>" not in item.reply_preview
    assert "Sure! Here is the architecture" in item.reply_preview
    assert item.message_count == 2


def test_build_outline_multiturn_with_tools() -> None:
    now = datetime.datetime.now(datetime.timezone.utc)
    messages = [
        MessageDTO(
            id="u-1",
            chat_id="c-1",
            role="user",
            content="First question",
            created_at=now,
        ),
        MessageDTO(
            id="t-1",
            chat_id="c-1",
            role="tool",
            content="Tool result content",
            created_at=now,
        ),
        MessageDTO(
            id="a-1",
            chat_id="c-1",
            role="assistant",
            content="First reply",
            created_at=now,
        ),
        MessageDTO(
            id="u-2",
            chat_id="c-1",
            role="user",
            content="Second question",
            created_at=now,
        ),
        MessageDTO(
            id="a-2",
            chat_id="c-1",
            role="assistant",
            content="Second reply",
            created_at=now,
        ),
    ]

    outlines = TurnOutlineProjectionService.build_outline_from_messages(messages)
    assert len(outlines) == 2
    assert outlines[0].turn_index == 1
    assert outlines[0].message_count == 3
    assert outlines[0].prompt_preview == "First question"
    assert outlines[0].reply_preview == "First reply"

    assert outlines[1].turn_index == 2
    assert outlines[1].message_count == 2
    assert outlines[1].prompt_preview == "Second question"
    assert outlines[1].reply_preview == "Second reply"
