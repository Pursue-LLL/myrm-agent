from __future__ import annotations

from datetime import datetime, timezone

from app.database.dto import MessageDTO
from app.services.chat.turn_outline_service import (
    TurnOutlineProjectionService,
    _sanitize_preview_text,
)


def test_sanitize_preview_text() -> None:
    assert _sanitize_preview_text("   hello   world\n\nnew line  ", 50) == "hello world new line"
    long_str = "a" * 100
    res = _sanitize_preview_text(long_str, 20)
    assert len(res) == 23
    assert res.endswith("...")


def test_turn_outline_projection_empty() -> None:
    outlines = TurnOutlineProjectionService.build_outline_from_messages([])
    assert outlines == []


def test_turn_outline_projection_multi_turn() -> None:
    now = datetime.now(timezone.utc)
    messages = [
        MessageDTO(
            id="msg-u1",
            chat_id="chat-1",
            role="user",
            content="Can you help me refactor the database schema?",
            sent_at=now,
            sent_timezone="UTC",
            created_at=now,
        ),
        MessageDTO(
            id="msg-a1",
            chat_id="chat-1",
            role="assistant",
            content="<think>Analyzing schema...</think>Sure! Let's start by looking at the existing tables.",
            sent_at=now,
            sent_timezone="UTC",
            created_at=now,
        ),
        MessageDTO(
            id="msg-u2",
            chat_id="chat-1",
            role="user",
            content="What about the migration script?",
            sent_at=now,
            sent_timezone="UTC",
            created_at=now,
        ),
        MessageDTO(
            id="msg-a2",
            chat_id="chat-1",
            role="assistant",
            content="Here is the migration script step by step.",
            sent_at=now,
            sent_timezone="UTC",
            created_at=now,
        ),
    ]

    outlines = TurnOutlineProjectionService.build_outline_from_messages(messages)
    assert len(outlines) == 2

    turn1 = outlines[0]
    assert turn1.turn_index == 1
    assert turn1.user_message_id == "msg-u1"
    assert turn1.assistant_message_id == "msg-a1"
    assert "refactor the database schema" in turn1.prompt_preview
    assert "Sure! Let's start" in (turn1.reply_preview or "")
    assert "<think>" not in (turn1.reply_preview or "")

    turn2 = outlines[1]
    assert turn2.turn_index == 2
    assert turn2.user_message_id == "msg-u2"
    assert turn2.assistant_message_id == "msg-a2"
    assert "migration script" in turn2.prompt_preview
    assert "migration script step by step" in (turn2.reply_preview or "")
