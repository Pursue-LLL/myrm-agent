"""Unit & integration tests for external agent transcript synchronization service."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database.models import Base
from app.database.models.chat import Chat
from app.database.repositories.conversation_recall.sql import CONVERSATION_RECALL_SCHEMA_SQL
from app.services.memory.imports.external_transcript_sync import (
    ExternalTranscriptSyncService,
)

FIXTURE_PATH = Path(__file__).resolve().parents[2] / "fixtures" / "test_claude_code_transcript.jsonl"


@pytest_asyncio.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        for ddl in CONVERSATION_RECALL_SCHEMA_SQL:
            await conn.execute(text(ddl))

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.mark.asyncio
async def test_sync_file_creates_incognito_chat_and_watermark(db_session: AsyncSession, tmp_path: Path) -> None:
    assert FIXTURE_PATH.is_file(), f"Fixture missing at {FIXTURE_PATH}"

    wm_file = tmp_path / "watermarks.json"
    service = ExternalTranscriptSyncService(watermark_path=wm_file)
    watermarks: dict[str, dict[str, object]] = {}

    turns_count, chat_id = await service.sync_file(db_session, FIXTURE_PATH, source="external:claude_code", watermarks=watermarks)
    await db_session.commit()

    assert turns_count == 3
    assert chat_id is not None
    assert chat_id.startswith("ext_claude_code_")

    # Verify chat row was created with incognito isolation
    stmt = select(Chat).where(Chat.id == chat_id)
    chat = (await db_session.execute(stmt)).scalar_one_or_none()
    assert chat is not None
    assert chat.is_incognito is True
    assert chat.source == "external:claude_code"

    # Verify watermark was recorded
    path_key = str(FIXTURE_PATH.resolve())
    assert path_key in watermarks
    assert int(watermarks[path_key]["offset"]) > 0

    # Second run without changes should skip
    re_turns, re_chat = await service.sync_file(db_session, FIXTURE_PATH, source="external:claude_code", watermarks=watermarks)
    assert re_turns == 0
    assert re_chat is None


@pytest.mark.asyncio
async def test_sync_file_scrubs_secrets_before_indexing(db_session: AsyncSession, tmp_path: Path) -> None:
    sensitive_file = tmp_path / "sensitive.jsonl"
    line1 = (
        json.dumps(
            {
                "type": "user",
                "message": {
                    "role": "user",
                    "content": "My OpenAI key is sk-12345678901234567890abcdef and token is Bearer super-secret-bearer-token-12345",
                },
            }
        )
        + "\n"
    )
    line2 = (
        json.dumps(
            {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": 'Received secret. Password is password="topsecret123"',
                },
            }
        )
        + "\n"
    )
    sensitive_file.write_text(line1 + line2, encoding="utf-8")

    service = ExternalTranscriptSyncService(watermark_path=tmp_path / "wm.json")
    turns_count, chat_id = await service.sync_file(db_session, sensitive_file)
    await db_session.commit()

    assert turns_count == 1
    assert chat_id is not None

    # Check that recall document has scrubbed text
    doc_res = await db_session.execute(
        text("SELECT searchable_text FROM conversation_recall_documents WHERE chat_id = :cid"),
        {"cid": chat_id},
    )
    row = doc_res.fetchone()
    assert row is not None
    searchable_text = row[0]
    assert "[REDACTED_API_KEY]" in searchable_text
    assert "sk-12345678901234567890" not in searchable_text
    assert "[REDACTED_TOKEN]" in searchable_text
    assert "super-secret-bearer-token" not in searchable_text


@pytest.mark.asyncio
async def test_sync_directory_scans_and_persists_watermarks(db_session: AsyncSession, tmp_path: Path) -> None:
    proj_dir = tmp_path / "claude_projects"
    sub_dir = proj_dir / "project_alpha"
    sub_dir.mkdir(parents=True)

    file_a = sub_dir / "chat_1.jsonl"
    file_b = sub_dir / "chat_2.jsonl"

    turn_data = (
        json.dumps(
            {
                "type": "user",
                "message": {"role": "user", "content": "How to configure SQLite?"},
            }
        )
        + "\n"
        + json.dumps(
            {
                "type": "assistant",
                "message": {"role": "assistant", "content": "Use PRAGMA journal_mode=WAL;"},
            }
        )
        + "\n"
    )

    file_a.write_text(turn_data, encoding="utf-8")
    file_b.write_text(turn_data, encoding="utf-8")

    wm_file = tmp_path / "data" / "watermarks.json"
    service = ExternalTranscriptSyncService(watermark_path=wm_file)

    res = await service.sync_directory(db_session, proj_dir, source="external:claude_code")
    await db_session.commit()

    assert res.synced_files == 2
    assert res.new_turns == 2
    assert len(res.affected_chats) == 2
    assert res.skipped_files == 0
    assert len(res.errors) == 0

    # Ensure watermark file was written to disk
    assert wm_file.is_file()
    loaded_wm = service.load_watermarks()
    assert len(loaded_wm) == 2

    # Second pass should skip all unmodified files
    res2 = await service.sync_directory(db_session, proj_dir, source="external:claude_code")
    assert res2.synced_files == 0
    assert res2.new_turns == 0
    assert res2.skipped_files == 2


@pytest.mark.asyncio
async def test_sync_file_incremental_append_growth(db_session: AsyncSession, tmp_path: Path) -> None:
    grow_file = tmp_path / "growing_session.jsonl"
    wm_file = tmp_path / "wm_grow.json"
    service = ExternalTranscriptSyncService(watermark_path=wm_file)
    watermarks: dict[str, dict[str, object]] = {}

    # Write first turn
    turn1 = (
        json.dumps(
            {
                "type": "user",
                "message": {"role": "user", "content": "First turn prompt"},
            }
        )
        + "\n"
        + json.dumps(
            {
                "type": "assistant",
                "message": {"role": "assistant", "content": "First turn response"},
            }
        )
        + "\n"
    )
    grow_file.write_text(turn1, encoding="utf-8")

    turns1, cid1 = await service.sync_file(db_session, grow_file, watermarks=watermarks)
    assert turns1 == 1
    offset_after_first = int(watermarks[str(grow_file.resolve())]["offset"])

    # Append second turn to the same file
    turn2 = (
        json.dumps(
            {
                "type": "user",
                "message": {"role": "user", "content": "Second turn prompt"},
            }
        )
        + "\n"
        + json.dumps(
            {
                "type": "assistant",
                "message": {"role": "assistant", "content": "Second turn response"},
            }
        )
        + "\n"
    )
    with open(grow_file, "a", encoding="utf-8") as f:
        f.write(turn2)

    turns2, cid2 = await service.sync_file(db_session, grow_file, watermarks=watermarks)
    assert turns2 == 1
    assert cid2 == cid1
    offset_after_second = int(watermarks[str(grow_file.resolve())]["offset"])
    assert offset_after_second > offset_after_first


@pytest.mark.asyncio
async def test_sync_file_truncation_or_rotation_recovery(db_session: AsyncSession, tmp_path: Path) -> None:
    rotate_file = tmp_path / "rotating_session.jsonl"
    wm_file = tmp_path / "wm_rotate.json"
    service = ExternalTranscriptSyncService(watermark_path=wm_file)
    watermarks: dict[str, dict[str, object]] = {}

    initial_content = (
        json.dumps(
            {
                "type": "user",
                "message": {"role": "user", "content": "Initial prompt before truncation"},
            }
        )
        + "\n"
        + json.dumps(
            {
                "type": "assistant",
                "message": {"role": "assistant", "content": "Initial long response" * 5},
            }
        )
        + "\n"
    )
    rotate_file.write_text(initial_content, encoding="utf-8")

    turns1, cid1 = await service.sync_file(db_session, rotate_file, watermarks=watermarks)
    assert turns1 == 1

    # Truncate and rewrite with smaller content (simulating rotation/rewrite)
    smaller_content = (
        json.dumps(
            {
                "type": "user",
                "message": {"role": "user", "content": "New shorter session"},
            }
        )
        + "\n"
        + json.dumps(
            {
                "type": "assistant",
                "message": {"role": "assistant", "content": "Short reply"},
            }
        )
        + "\n"
    )
    assert len(smaller_content.encode("utf-8")) < len(initial_content.encode("utf-8"))
    rotate_file.write_text(smaller_content, encoding="utf-8")

    turns2, cid2 = await service.sync_file(db_session, rotate_file, watermarks=watermarks)
    assert turns2 == 1
    assert cid2 == cid1
    assert watermarks[str(rotate_file.resolve())]["offset"] == len(smaller_content.encode("utf-8"))


@pytest.mark.asyncio
async def test_sync_empty_or_nonexistent_file(db_session: AsyncSession, tmp_path: Path) -> None:
    service = ExternalTranscriptSyncService()
    turns, cid = await service.sync_file(db_session, tmp_path / "nonexistent.jsonl")
    assert turns == 0
    assert cid is None

    empty_file = tmp_path / "empty.jsonl"
    empty_file.write_text("", encoding="utf-8")
    turns_empty, cid_empty = await service.sync_file(db_session, empty_file)
    assert turns_empty == 0
    assert cid_empty is None
