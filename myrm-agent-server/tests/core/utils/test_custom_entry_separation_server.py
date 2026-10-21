"""Tests for server-side custom entry vs custom_message separation.

Verifies:
1. convert_chat_history ignores role="custom" entries (zero token leak).
2. convert_chat_history converts role="custom_message" to HumanMessage with metadata.
3. db_messages_to_langchain excludes ephemeral messages from compaction summarization.
4. _empty_trace_payload surfaces custom_states.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from app.api.statistics.session_trace_enrichment import _empty_trace_payload
from app.core.utils.chat_utils import convert_chat_history
from app.database.models import Message
from app.services.chat.compact.message_io import db_messages_to_langchain


@pytest.mark.asyncio
async def test_convert_chat_history_skips_custom_state_and_converts_custom_message() -> None:
    history = [
        ["human", "Please check my project status"],
        ["assistant", "Checking your project now..."],
        # Custom state entry: must be SKIPPED completely
        ["custom", {"cached_ast": {"node_count": 500, "hash": "abc12345"}}],
        # Custom message entry: must be converted to HumanMessage with metadata
        [
            "custom_message",
            "Environment notice: Sandbox has only 2GB RAM remaining",
            {
                "custom_type": "resource_monitor",
                "display": True,
                "retention": "ephemeral",
                "details": {"remaining_mb": 2048},
            },
        ],
    ]

    messages = await convert_chat_history(history)
    # Total messages: 1 human + 1 assistant + 0 custom (skipped) + 1 custom_message = 3
    assert len(messages) == 3

    assert isinstance(messages[0], HumanMessage)
    assert messages[0].content == "Please check my project status"

    assert isinstance(messages[1], AIMessage)
    assert messages[1].content == "Checking your project now..."

    assert isinstance(messages[2], HumanMessage)
    assert messages[2].content == "Environment notice: Sandbox has only 2GB RAM remaining"
    assert messages[2].additional_kwargs.get("is_custom_message") is True
    assert messages[2].additional_kwargs.get("custom_type") == "resource_monitor"
    assert messages[2].additional_kwargs.get("display") is True
    assert messages[2].additional_kwargs.get("retention") == "ephemeral"
    assert messages[2].additional_kwargs.get("details") == {"remaining_mb": 2048}


def test_db_messages_to_langchain_excludes_ephemeral() -> None:
    now = datetime.now(timezone.utc)
    m1 = Message(
        id="m1",
        chat_id="chat-1",
        role="user",
        content="First question",
        sent_at=now,
        sent_timezone="UTC",
    )
    m2 = Message(
        id="m2",
        chat_id="chat-1",
        role="assistant",
        content="First answer",
        sent_at=now,
        sent_timezone="UTC",
    )
    # Ephemeral custom message: should NOT be included in compaction summary!
    m3_ephemeral = Message(
        id="m3",
        chat_id="chat-1",
        role="custom_message",
        content="Temporary warning: rate limit near 80%",
        sent_at=now,
        sent_timezone="UTC",
        extra_data={"is_custom_message": True, "retention": "ephemeral"},
    )
    # Persistent custom message: should be included in compaction summary
    m4_persistent = Message(
        id="m4",
        chat_id="chat-1",
        role="custom_message",
        content="Persistent constraint: All SQL must be Postgres-compatible",
        sent_at=now,
        sent_timezone="UTC",
        extra_data={"is_custom_message": True, "retention": "persistent"},
    )

    lc_msgs = db_messages_to_langchain([m1, m2, m3_ephemeral, m4_persistent])
    assert len(lc_msgs) == 3
    assert lc_msgs[0].content == "First question"
    assert lc_msgs[1].content == "First answer"
    assert lc_msgs[2].content == "Persistent constraint: All SQL must be Postgres-compatible"


def test_empty_trace_payload_contains_custom_states() -> None:
    payload = _empty_trace_payload("test-session-123", [])
    assert "custom_states" in payload
    assert payload["custom_states"] == {}
