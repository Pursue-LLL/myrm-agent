"""Unit tests for TurnOutlineProjectionService and API endpoints."""

from __future__ import annotations

from datetime import datetime, timezone

from app.database.dto import MessageDTO
from app.services.chat.turn_outline_service import (
    TurnOutlineProjectionService,
    _sanitize_preview_text,
)


def test_sanitize_preview_text() -> None:
    raw_markdown = "### Hello World\n\nThis is a *test* query with multiple    spaces and \nnewlines."
    cleaned = _sanitize_preview_text(raw_markdown, max_chars=30)
    assert len(cleaned) <= 33
    assert "\n" not in cleaned
    assert "###" in cleaned or "Hello" in cleaned


def test_build_outline_from_messages_empty() -> None:
    outlines = TurnOutlineProjectionService.build_outline_from_messages([])
    assert outlines == []


def test_build_outline_from_messages_multi_turn() -> None:
    now = datetime.now(timezone.utc)
    messages = [
        MessageDTO(
            id="msg_u1",
            chat_id="chat_1",
            role="user",
            content="Please write a fibonacci script in Python.",
            created_at=now,
            sent_at=now,
            sent_timezone="UTC",
            is_active=True,
        ),
        MessageDTO(
            id="msg_a1",
            chat_id="chat_1",
            role="assistant",
            content="<think>Need to generate fibonacci</think>Here is the recursive and iterative Python code.",
            created_at=now,
            sent_at=now,
            sent_timezone="UTC",
            is_active=True,
        ),
        MessageDTO(
            id="msg_u2",
            chat_id="chat_1",
            role="user",
            content="Can you optimize it using dynamic programming?",
            created_at=now,
            sent_at=now,
            sent_timezone="UTC",
            is_active=True,
        ),
        MessageDTO(
            id="msg_a2",
            chat_id="chat_1",
            role="assistant",
            content="Certainly! We can use memoization or bottom-up tabulation to achieve O(n) time.",
            created_at=now,
            sent_at=now,
            sent_timezone="UTC",
            is_active=True,
        ),
    ]

    outlines = TurnOutlineProjectionService.build_outline_from_messages(messages)
    assert len(outlines) == 2

    # Turn 1
    assert outlines[0].turn_index == 1
    assert outlines[0].user_message_id == "msg_u1"
    assert outlines[0].assistant_message_id == "msg_a1"
    assert "fibonacci" in outlines[0].prompt_preview
    assert "<think>" not in (outlines[0].reply_preview or "")
    assert "recursive" in (outlines[0].reply_preview or "")
    assert outlines[0].message_count == 2

    # Turn 2
    assert outlines[1].turn_index == 2
    assert outlines[1].user_message_id == "msg_u2"
    assert outlines[1].assistant_message_id == "msg_a2"
    assert "optimize" in outlines[1].prompt_preview
    assert "memoization" in (outlines[1].reply_preview or "")
    assert outlines[1].message_count == 2
