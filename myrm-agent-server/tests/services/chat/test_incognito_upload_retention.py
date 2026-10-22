"""What a web incognito chat uploaded leaves with the chat: the hourly purge removes it.

The scenarios run the real purge against a real schema and a real ``FilesService`` on a scratch directory; the slow
disposal collaborators are recorded by spies. An upload is bound to its chat only when the chat is incognito, so
every other upload must survive whatever the purge does.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from myrm_agent_harness.toolkits.storage.local import LocalStorageBackend
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.storage import File, FilePurpose, FilesService
from app.core.storage.chat_bound import pdf_extract_source
from app.core.storage.paths import get_file_metadata_path
from app.database.models import Chat
from app.services.chat import chat_retention
from tests.services.chat.disposal_support import install_spies, point_event_log_at_scratch

INCOGNITO_CHAT = "chat-incognito"
LIVE_INCOGNITO_CHAT = "chat-incognito-live"
NORMAL_CHAT = "chat-normal"


@pytest.fixture
def service(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> FilesService:
    install_spies(monkeypatch)
    point_event_log_at_scratch(tmp_path, monkeypatch)
    scratch = FilesService(LocalStorageBackend(tmp_path / "storage"))
    monkeypatch.setattr(chat_retention, "files_service", scratch)
    return scratch


async def _seed_chat(db: AsyncSession, chat_id: str, *, incognito: bool, idle_for: timedelta) -> None:
    moment = datetime.now(UTC).replace(tzinfo=None) - idle_for
    db.add(Chat(id=chat_id, title="t", source="web", is_incognito=incognito, created_at=moment, updated_at=moment))
    await db.commit()


async def _backdate(service: FilesService, file: File, age: timedelta) -> None:
    file.created_at = datetime.now(UTC).replace(tzinfo=None) - age
    await service.storage.write_text(get_file_metadata_path(file.storage_path), json.dumps(file.to_dict()))


async def _on_disk(service: FilesService) -> set[str]:
    return {file.id for file in await service.list_files(include_expired=True)}


@pytest.mark.asyncio
async def test_the_purge_removes_the_uploads_of_the_chats_it_deletes(db_session: AsyncSession, service: FilesService) -> None:
    await _seed_chat(db_session, INCOGNITO_CHAT, incognito=True, idle_for=timedelta(hours=2))
    await _seed_chat(db_session, LIVE_INCOGNITO_CHAT, incognito=True, idle_for=timedelta(minutes=5))
    doomed = await service.upload_file("tax-return.pdf", b"x", source_chat_id=INCOGNITO_CHAT)
    doomed_page = await service.save_generated_file(
        "pdf-page-1.png", b"png", "image/png", source_chat_id=pdf_extract_source(doomed.id)
    )
    still_open = await service.upload_file("draft.txt", b"x", source_chat_id=LIVE_INCOGNITO_CHAT)
    shared = await service.upload_file("notes.txt", b"x")

    assert await chat_retention.purge_idle_incognito_chats() == 1

    assert await _on_disk(service) == {still_open.id, shared.id}
    assert doomed.id not in await _on_disk(service)
    assert doomed_page.id not in await _on_disk(service)


@pytest.mark.asyncio
async def test_the_purge_sweeps_uploads_whose_chat_never_got_a_row_once_the_grace_period_is_over(
    db_session: AsyncSession, service: FilesService
) -> None:
    """A chat row appears only with the first reply, so an upload that was never sent has no chat to be removed with."""
    abandoned = await service.upload_file("abandoned.pdf", b"x", source_chat_id="chat-never-persisted")
    recent = await service.upload_file("recent.pdf", b"x", source_chat_id="chat-not-persisted-yet")
    await _backdate(service, abandoned, chat_retention.INCOGNITO_UPLOAD_ORPHAN_GRACE + timedelta(minutes=1))
    await _backdate(service, recent, chat_retention.INCOGNITO_UPLOAD_ORPHAN_GRACE - timedelta(minutes=1))

    assert await chat_retention.purge_idle_incognito_chats() == 0

    assert await _on_disk(service) == {recent.id}


@pytest.mark.asyncio
async def test_the_purge_never_removes_unbound_uploads_or_uploads_of_a_chat_that_exists(
    db_session: AsyncSession, service: FilesService
) -> None:
    await _seed_chat(db_session, NORMAL_CHAT, incognito=False, idle_for=timedelta(days=60))
    unbound = await service.upload_file("old.pdf", b"x")
    of_existing = await service.upload_file("kept.pdf", b"x", source_chat_id=NORMAL_CHAT)
    for file in (unbound, of_existing):
        await _backdate(service, file, timedelta(days=90))

    assert await chat_retention.purge_idle_incognito_chats() == 0

    assert await _on_disk(service) == {unbound.id, of_existing.id}


@pytest.mark.asyncio
async def test_a_storage_failure_does_not_undo_or_fail_the_chat_purge(
    db_session: AsyncSession, service: FilesService, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _seed_chat(db_session, INCOGNITO_CHAT, incognito=True, idle_for=timedelta(hours=2))
    leftover = await service.upload_file("tax-return.pdf", b"x", source_chat_id=INCOGNITO_CHAT)

    real_list_files = service.list_files
    failures = [OSError("storage unavailable")]

    async def fails_once(purpose: FilePurpose | None = None, include_expired: bool = False) -> list[File]:
        if failures:
            raise failures.pop()
        return await real_list_files(purpose=purpose, include_expired=include_expired)

    monkeypatch.setattr(service, "list_files", fails_once)

    assert await chat_retention.purge_idle_incognito_chats() == 1
    assert await _on_disk(service) == {leftover.id}

    # The chat is gone by now, so the next run selects the leftover as soon as it has outlived the grace period.
    await _backdate(service, leftover, chat_retention.INCOGNITO_UPLOAD_ORPHAN_GRACE + timedelta(minutes=1))
    assert await chat_retention.purge_idle_incognito_chats() == 0
    assert await _on_disk(service) == set()
