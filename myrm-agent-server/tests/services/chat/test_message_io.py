"""Tests for compact.message_io — summary deserialization across the DB boundary.

``parse_existing_summary`` must survive all 14 ``StructuredSummary`` fields so
incremental compaction bases its merge on a complete prior summary, not a
5-field subset that silently drops constraints, pending asks, and next steps.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from app.database.models import Chat, Message
from app.services.chat.compact.message_io import (
    backup_context,
    db_messages_to_langchain,
    load_chat,
    load_compactable_messages,
    parse_existing_summary,
)


def test_parse_existing_summary_full_fields() -> None:
    payload = {
        "user_goal": "build feature",
        "completed_actions": ["step1"],
        "key_findings": ["found bug"],
        "errors_and_fixes": ["crash -> null check"],
        "files_modified": ["main.py"],
        "last_action": "fixed",
        "active_task": "add tests",
        "constraints_and_preferences": ["use TS"],
        "resolved_questions": ["Q -> A"],
        "pending_user_asks": ["update docs"],
        "active_state": "dev branch",
        "blocked_items": ["dep conflict"],
        "next_steps": ["run pytest"],
    }
    summary = parse_existing_summary(json.dumps(payload))
    assert summary is not None
    assert summary.user_goal == "build feature"
    assert summary.completed_actions == ["step1"]
    assert summary.key_findings == ["found bug"]
    assert summary.errors_and_fixes == ["crash -> null check"]
    assert summary.files_modified == ["main.py"]
    assert summary.last_action == "fixed"
    assert summary.active_task == "add tests"
    assert summary.constraints_and_preferences == ["use TS"]
    assert summary.resolved_questions == ["Q -> A"]
    assert summary.pending_user_asks == ["update docs"]
    assert summary.active_state == "dev branch"
    assert summary.blocked_items == ["dep conflict"]
    assert summary.next_steps == ["run pytest"]


def test_parse_existing_summary_missing_fields_default_empty() -> None:
    summary = parse_existing_summary('{"user_goal": "minimal"}')
    assert summary is not None
    assert summary.user_goal == "minimal"
    assert summary.completed_actions == []
    assert summary.blocked_items == []
    assert summary.next_steps == []


def test_parse_existing_summary_invalid_returns_none() -> None:
    assert parse_existing_summary("{not valid json") is None
    assert parse_existing_summary(None) is None  # type: ignore[arg-type]


def test_parse_existing_summary_roundtrip_keeps_blocked_and_next() -> None:
    from myrm_agent_harness.agent.context_management.infra.schemas import (
        StructuredSummary,
    )

    original = StructuredSummary(
        user_goal="goal",
        completed_actions=["a"],
        blocked_items=["blocker"],
        next_steps=["next"],
        constraints_and_preferences=["c"],
        pending_user_asks=["p"],
    )
    parsed = parse_existing_summary(original.to_json())
    assert parsed is not None
    assert parsed.user_goal == "goal"
    assert parsed.blocked_items == ["blocker"]
    assert parsed.next_steps == ["next"]
    assert parsed.constraints_and_preferences == ["c"]
    assert parsed.pending_user_asks == ["p"]


def _make_message(
    chat_id: str,
    index: int,
    *,
    role: str = "user",
    created_at: datetime | None = None,
) -> Message:
    now = created_at or datetime.now(UTC)
    return Message(
        id=f"msg-{chat_id}-{index}",
        chat_id=chat_id,
        role=role,
        content=f"message {index}",
        sent_at=now,
        sent_timezone="UTC",
        created_at=now,
    )


@pytest.mark.asyncio
async def test_load_chat_returns_chat() -> None:
    db = AsyncMock()
    expected = Chat(id="chat-load", compacted_summary=None)
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = expected
    db.execute.return_value = result_mock

    result = await load_chat(db, "chat-load")

    assert result is expected
    db.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_load_chat_returns_none_when_missing() -> None:
    db = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    db.execute.return_value = result_mock

    result = await load_chat(db, "chat-missing")

    assert result is None


@pytest.mark.asyncio
async def test_load_compactable_messages_without_anchor() -> None:
    db = AsyncMock()
    chat = Chat(id="chat-plain", compacted_before_id=None)
    messages = [_make_message("chat-plain", 0), _make_message("chat-plain", 1)]
    result_mock = MagicMock()
    result_mock.scalars.return_value.all.return_value = messages
    db.execute.return_value = result_mock

    result = await load_compactable_messages(db, chat)

    assert result == messages
    assert db.execute.await_count == 1


@pytest.mark.asyncio
async def test_load_compactable_messages_with_anchor_filters_after() -> None:
    db = AsyncMock()
    anchor_ts = datetime(2026, 8, 1, tzinfo=UTC)
    chat = Chat(id="chat-anchor", compacted_before_id="msg-anchor")
    messages = [_make_message("chat-anchor", 9, created_at=anchor_ts)]
    anchor_mock = MagicMock()
    anchor_mock.scalar_one_or_none.return_value = anchor_ts
    result_mock = MagicMock()
    result_mock.scalars.return_value.all.return_value = messages
    db.execute.side_effect = [anchor_mock, result_mock]

    result = await load_compactable_messages(db, chat)

    assert result == messages
    assert db.execute.await_count == 2


@pytest.mark.asyncio
async def test_load_compactable_messages_with_anchor_missing_ts() -> None:
    db = AsyncMock()
    chat = Chat(id="chat-anchor-missing", compacted_before_id="msg-gone")
    anchor_mock = MagicMock()
    anchor_mock.scalar_one_or_none.return_value = None
    result_mock = MagicMock()
    result_mock.scalars.return_value.all.return_value = []
    db.execute.side_effect = [anchor_mock, result_mock]

    result = await load_compactable_messages(db, chat)

    assert result == []
    assert db.execute.await_count == 2


def test_db_messages_to_langchain_maps_user_and_assistant() -> None:
    chat_id = "chat-lc"
    messages = [
        _make_message(chat_id, 0, role="user"),
        _make_message(chat_id, 1, role="assistant"),
        _make_message(chat_id, 2, role="tool"),
    ]

    converted = db_messages_to_langchain(messages)

    assert len(converted) == 2
    assert isinstance(converted[0], HumanMessage)
    assert isinstance(converted[1], AIMessage)
    assert converted[0].content == "message 0"
    assert converted[1].content == "message 1"


@pytest.mark.asyncio
async def test_backup_context_writes_jsonl() -> None:
    chat = Chat(
        id="chat-backup",
        compacted_summary='{"user_goal": "prior"}',
        compacted_before_id=None,
    )
    messages = [_make_message("chat-backup", 0, role="user")]
    storage = AsyncMock()

    with patch(
        "app.platform_utils.get_storage_provider",
        return_value=storage,
    ):
        result = await backup_context(chat, messages)

    assert result is not None
    assert result.startswith(".myrm/chat_backups/chat-backup/")
    assert result.endswith(".jsonl")
    storage.write.assert_awaited_once()
    written = storage.write.await_args.args[1].decode()
    assert '"type": "previous_summary"' in written
    assert '"role": "user"' in written


@pytest.mark.asyncio
async def test_backup_context_returns_none_on_failure() -> None:
    chat = Chat(id="chat-backup-fail", compacted_summary=None)
    storage = AsyncMock()
    storage.write.side_effect = RuntimeError("disk full")

    with patch(
        "app.platform_utils.get_storage_provider",
        return_value=storage,
    ):
        result = await backup_context(chat, [])

    assert result is None
