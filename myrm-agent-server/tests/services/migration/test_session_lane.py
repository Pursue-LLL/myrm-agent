"""Tests for SessionMigrationService and competitor transcript integration.

[INPUT]
- app.services.migration.session_lane::SessionMigrationService
- app.services.migration.source.source_payload_loaders_impl::load_claude, load_codex
- app.database.models::Chat, Message

[OUTPUT]
- Verifies session preview creation
- Verifies session confirmation and DB persistence into chats/messages
- Verifies Claude/Codex filesystem discovery and transcript loading

[POS]
tests/services/migration/test_session_lane.py
Ensures zero-friction competitor session migration without prompt-cache disruption.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from myrm_agent_harness.runtime.context.transcripts import (
    CanonicalToolCall,
    CanonicalTranscriptTurn,
    CanonicalTurnRole,
    TranscriptParseResult,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.database.models import Base, Chat, Message
from app.services.migration.session_lane import SessionMigrationService
from app.services.migration.source.source_payload_loaders_impl import load_claude, load_codex, load_hermes


@pytest.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    """In-memory SQLite session with all tables created."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session

    await engine.dispose()


def test_session_migration_preview() -> None:
    turn1 = CanonicalTranscriptTurn(
        turn_id="t1",
        role=CanonicalTurnRole.USER,
        content="Fix the database connection timeout issue",
        timestamp=1700000000.0,
    )
    turn2 = CanonicalTranscriptTurn(
        turn_id="t2",
        role=CanonicalTurnRole.ASSISTANT,
        content="I will inspect the HikariCP configuration.",
        tool_calls=[
            CanonicalToolCall(
                call_id="c1",
                tool_name="view_file",
                arguments={"path": "/workspace/db.go"},
                output="max_connections: 5",
            )
        ],
        timestamp=1700000005.0,
    )
    parse_result = TranscriptParseResult(
        session_id="session-timeout-fix",
        title="Fix database connection timeout",
        turns=[turn1, turn2],
        source_platform="claude_code",
        created_at=1700000000.0,
        updated_at=1700000005.0,
        detected_workspace_hint="/workspace",
        total_tool_calls=1,
    )

    previews = SessionMigrationService.build_preview([parse_result])
    assert len(previews) == 1
    p = previews[0]
    assert p.session_id == "session-timeout-fix"
    assert p.title == "Fix database connection timeout"
    assert p.turn_count == 2
    assert p.tool_call_count == 1
    assert p.source_platform == "claude_code"
    assert "2023" in p.created_at_iso


@pytest.mark.asyncio
async def test_session_migration_confirm(db_session: AsyncSession) -> None:
    turn1 = CanonicalTranscriptTurn(
        turn_id="t1",
        role=CanonicalTurnRole.USER,
        content="Hello from Claude Code import",
        timestamp=1700000000.0,
    )
    turn2 = CanonicalTranscriptTurn(
        turn_id="t2",
        role=CanonicalTurnRole.ASSISTANT,
        content="Hello! Here is the response with thought.",
        thinking_trace="Analyzing greeting",
        tool_calls=[
            CanonicalToolCall(
                call_id="call-99",
                tool_name="read_file",
                arguments={"file": "/workspace/main.py"},
                output="print('hello')",
            )
        ],
        timestamp=1700000002.0,
    )
    parse_result = TranscriptParseResult(
        session_id="test-session-001",
        title="Hello from Claude Code",
        turns=[turn1, turn2],
        source_platform="claude_code",
        created_at=1700000000.0,
        updated_at=1700000002.0,
        detected_workspace_hint="/workspace/repo",
        total_tool_calls=1,
    )

    service = SessionMigrationService(db_session)
    res = await service.confirm_sessions([parse_result], target_workspace_override="/workspace/my-app")

    assert res.imported_count == 1
    assert res.failed_count == 0
    assert len(res.created_chat_ids) == 1
    chat_id = res.created_chat_ids[0]

    # Verify chat row
    chat_row = (await db_session.execute(select(Chat).where(Chat.id == chat_id))).scalar_one_or_none()
    assert chat_row is not None
    assert chat_row.title == "Hello from Claude Code"
    assert chat_row.source == "claude_code"
    assert chat_row.workspace_dir == "/workspace/my-app"
    assert chat_row.first_message == "Hello from Claude Code import"

    # Verify message rows
    msg_rows = (
        await db_session.execute(select(Message).where(Message.chat_id == chat_id).order_by(Message.sent_at.asc()))
    ).scalars().all()
    assert len(msg_rows) == 2

    # Check user turn
    assert msg_rows[0].role == "user"
    assert msg_rows[0].content == "Hello from Claude Code import"

    # Check assistant turn with thought and tool calls
    assert msg_rows[1].role == "assistant"
    assert msg_rows[1].content == "Hello! Here is the response with thought."
    extra = msg_rows[1].extra_data or {}
    assert extra.get("thinking_trace") == "Analyzing greeting"
    tcs = extra.get("tool_calls")
    assert isinstance(tcs, list) and len(tcs) == 1
    assert tcs[0].get("tool_name") == "read_file"


def test_load_claude_with_sessions(tmp_path: Path) -> None:
    session_file = tmp_path / "sessions" / "test_session.jsonl"
    session_file.parent.mkdir(parents=True, exist_ok=True)

    events = [
        {"type": "user", "message": "Investigate memory leak", "timestamp": 1700000000.0, "cwd": "/host/repo"},
        {
            "type": "assistant",
            "text": "Running profiler.",
            "tool_uses": [{"id": "t1", "name": "Bash", "input": {"cmd": "valgrind"}}],
            "timestamp": 1700000005.0,
        },
    ]
    with open(session_file, "w", encoding="utf-8") as f:
        for ev in events:
            f.write(json.dumps(ev) + "\n")

    res = load_claude(tmp_path, [str(session_file)])
    assert "sessions" in res
    sessions = res["sessions"]
    assert isinstance(sessions, list) and len(sessions) == 1
    assert "Investigate memory leak" in str(sessions[0].get("title", ""))


def test_load_codex_with_sessions(tmp_path: Path) -> None:
    session_file = tmp_path / "sessions" / "session_123.json"
    session_file.parent.mkdir(parents=True, exist_ok=True)

    data = {
        "id": "codex-sess-1",
        "title": "Codex Refactoring Session",
        "created_at": 1700000000.0,
        "turns": [
            {
                "role": "user",
                "content": "Refactor auth middleware",
            },
            {
                "role": "assistant",
                "content": "Here is the refactored middleware.",
            },
        ],
    }
    with open(session_file, "w", encoding="utf-8") as f:
        json.dump(data, f)

    res = load_codex(tmp_path, [str(session_file)])
    assert "sessions" in res
    sessions = res["sessions"]
    assert isinstance(sessions, list) and len(sessions) == 1
    assert sessions[0].get("title") == "Codex Refactoring Session"


def test_load_hermes_with_sessions(tmp_path: Path) -> None:
    session_file = tmp_path / "sessions" / "session_999.json"
    session_file.parent.mkdir(parents=True, exist_ok=True)

    data = {
        "id": "hermes-sess-1",
        "title": "Hermes CI Debugging Session",
        "created_at": 1700000000.0,
        "messages": [
            {
                "role": "user",
                "content": "Check why CI build failed",
            },
            {
                "role": "assistant",
                "content": "Checking test runner logs now.",
            },
        ],
    }
    with open(session_file, "w", encoding="utf-8") as f:
        json.dump(data, f)

    res = load_hermes(tmp_path, [str(session_file)])
    assert "sessions" in res
    sessions = res["sessions"]
    assert isinstance(sessions, list) and len(sessions) == 1
    assert sessions[0].get("title") == "Hermes CI Debugging Session"

