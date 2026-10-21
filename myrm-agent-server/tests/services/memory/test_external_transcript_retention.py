"""Imported agent transcripts must outlive the incognito auto-purge.

The sync watermark lives in a file next to the database and only moves forward, so a turn whose recall index the
purge removed is never imported again. The scenario runs the real sync, the real purge and the real recall schema;
the slow disposal collaborators are recorded by spies and the event log points at a scratch directory.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Chat
from app.services.chat import chat_retention
from app.services.memory.imports.external_transcript_sync import ExternalTranscriptSyncService
from tests.services.chat.disposal_support import install_spies, point_event_log_at_scratch


def _turn(question: str, answer: str) -> str:
    user = {"type": "user", "message": {"role": "user", "content": question}}
    assistant = {"type": "assistant", "message": {"role": "assistant", "content": answer}}
    return json.dumps(user) + "\n" + json.dumps(assistant) + "\n"


async def _recall_documents(db: AsyncSession, chat_id: str) -> list[str]:
    rows = await db.execute(
        text("SELECT searchable_text FROM conversation_recall_documents WHERE chat_id = :chat_id"),
        {"chat_id": chat_id},
    )
    return [str(row[0]) for row in rows.all()]


@pytest.mark.asyncio
async def test_imported_history_survives_the_purge_and_the_next_sync(
    db_session: AsyncSession, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_spies(monkeypatch)
    point_event_log_at_scratch(tmp_path, monkeypatch)
    transcript = tmp_path / "session.jsonl"
    transcript.write_text(_turn("first question", "first answer"), encoding="utf-8")
    service = ExternalTranscriptSyncService(watermark_path=tmp_path / "watermarks.json")
    watermarks: dict[str, dict[str, object]] = {}

    _, chat_id = await service.sync_file(db_session, transcript, source="external:claude_code", watermarks=watermarks)
    assert chat_id is not None
    long_ago = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=2)
    await db_session.execute(update(Chat).where(Chat.id == chat_id).values(updated_at=long_ago))
    await db_session.commit()

    assert await chat_retention.purge_idle_incognito_chats() == 0

    with transcript.open("a", encoding="utf-8") as stream:
        stream.write(_turn("second question", "second answer"))
    await service.sync_file(db_session, transcript, source="external:claude_code", watermarks=watermarks)
    await db_session.commit()

    documents = await _recall_documents(db_session, chat_id)
    assert len(documents) == 1
    assert "first question" in documents[0]
    assert "second question" in documents[0]
