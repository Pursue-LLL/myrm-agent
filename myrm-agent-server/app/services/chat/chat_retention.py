"""Time-based permanent deletion of chats: expired trash and idle incognito sessions.

[INPUT]
- app.database.repositories.uow::UnitOfWork (POS: transactional repository access)
- app.database.repositories.chat_repo::ChatRepository (POS: chat persistence)
- app.services.chat.chat_service::ChatService (POS: chat lifecycle facade that owns the full deletion teardown)
- app.services.agent.gateway::get_agent_gateway (POS: which conversations have a turn in flight)
- app.core.storage::files_service (POS: the uploads an incognito chat bound to itself)
- app.core.storage.chat_bound (POS: which uploads belong to which chats, and their removal)

[OUTPUT]
- purge_expired_trash: permanently delete chats that stayed in the trash past the retention window
- purge_idle_incognito_chats: permanently delete idle web incognito chats that have no turn in flight, together
  with the uploads they bound to themselves
- INCOGNITO_UPLOAD_ORPHAN_GRACE: how long an upload may wait for its chat row before it counts as abandoned

[POS]
Retention policy for the scheduler. It only decides which chats are due and delegates the deletion to
``ChatService``, so an automatic purge tears down exactly what a manual one does.
"""

from __future__ import annotations

import logging
from collections.abc import Collection
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.core.storage import FilePurpose, files_service
from app.core.storage.chat_bound import chat_bound_uploads, delete_uploads_with_derivatives
from app.database.models import Chat
from app.database.repositories.chat_repo import ChatRepository
from app.database.repositories.uow import UnitOfWork
from app.services.agent.gateway import get_agent_gateway

from .chat_service import ChatService

logger = logging.getLogger(__name__)

TRASH_RETENTION = timedelta(days=30)
INCOGNITO_MAX_IDLE = timedelta(hours=1)
# A chat row is written with the first reply, so an upload can precede its chat by as long as the user takes to send.
INCOGNITO_UPLOAD_ORPHAN_GRACE = timedelta(hours=24)
_CHAT_ID_QUERY_CHUNK = 500


def _naive_utc_now() -> datetime:
    """Timestamps are stored as naive UTC, so cutoffs must be naive UTC as well."""
    return datetime.now(UTC).replace(tzinfo=None)


async def purge_expired_trash() -> int:
    """Permanently delete chats trashed longer than ``TRASH_RETENTION``; return how many were deleted."""
    async with UnitOfWork() as uow:
        session = uow.session
        assert session is not None
        chat_ids = await ChatRepository.get_expired_trashed_chat_ids(session, _naive_utc_now() - TRASH_RETENTION)

    deleted = 0
    for chat_id in chat_ids:
        try:
            if await ChatService.permanently_delete_chat(chat_id):
                deleted += 1
        except Exception as exc:
            logger.warning("Chat trash auto-purge failed (chat=%s): %s", chat_id, exc)
    if deleted:
        logger.info("Chat trash auto-purge: %d expired chats permanently deleted", deleted)
    return deleted


async def purge_idle_incognito_chats() -> int:
    """Permanently delete idle incognito chats the user started on the web; return how many were deleted.

    Only ``source == "web"`` chats qualify. Transcript imports set ``is_incognito`` just to stay out of the
    sidebar, and their sync watermark never re-imports what a purge removes. A chat with a turn in flight is
    skipped and picked up by a later run. The uploads those chats bound to themselves go with them, and so do
    uploads whose chat never got a row (see ``purge_incognito_uploads``).
    """
    cutoff = _naive_utc_now() - INCOGNITO_MAX_IDLE
    async with UnitOfWork() as uow:
        session = uow.session
        assert session is not None
        rows = await session.execute(
            select(Chat.id).where(Chat.is_incognito.is_(True), Chat.source == "web", Chat.updated_at < cutoff)
        )
        chat_ids = [row[0] for row in rows.all()]

    gateway = get_agent_gateway()
    purged: list[str] = []
    for chat_id in chat_ids:
        if chat_id in gateway.active_session_ids():
            continue
        try:
            # Permanent deletion only accepts trashed chats; its teardown already covers what a soft delete stops.
            async with UnitOfWork() as uow:
                await uow.chat_repo.soft_delete_chat(chat_id)
            if await ChatService.permanently_delete_chat(chat_id):
                purged.append(chat_id)
        except Exception as exc:
            logger.warning("Incognito chat auto-purge failed (chat=%s): %s", chat_id, exc)
    if purged:
        logger.info("Incognito chat auto-purge: %d expired incognito chats permanently deleted", len(purged))

    try:
        removed = await purge_incognito_uploads(purged)
    except Exception as exc:
        # The chats are already gone; what is left is selected again by the next run.
        logger.warning("Incognito upload auto-purge failed: %s", exc)
    else:
        if removed:
            logger.info("Incognito upload auto-purge: %d files deleted", removed)
    return len(purged)


async def purge_incognito_uploads(purged_chat_ids: Collection[str]) -> int:
    """Delete uploads bound to a chat that no longer exists; return how many files were removed.

    Uploads of ``purged_chat_ids`` go at once. The rest wait out ``INCOGNITO_UPLOAD_ORPHAN_GRACE``, because
    a chat that has no row yet looks the same as one that never will.
    """
    bound = chat_bound_uploads(await files_service.list_files(purpose=FilePurpose.UPLOAD, include_expired=True))
    owners = {file.source_chat_id for file in bound if file.source_chat_id}
    if not owners:
        return 0
    gone = owners - await _existing_chat_ids(owners)
    abandoned_before = _naive_utc_now() - INCOGNITO_UPLOAD_ORPHAN_GRACE
    doomed = [
        file
        for file in bound
        if file.source_chat_id in gone and (file.source_chat_id in purged_chat_ids or file.created_at < abandoned_before)
    ]
    return await delete_uploads_with_derivatives(files_service, doomed)


async def _existing_chat_ids(chat_ids: Collection[str]) -> set[str]:
    ordered = sorted(chat_ids)
    found: set[str] = set()
    async with UnitOfWork() as uow:
        session = uow.session
        assert session is not None
        for start in range(0, len(ordered), _CHAT_ID_QUERY_CHUNK):
            rows = await session.execute(select(Chat.id).where(Chat.id.in_(ordered[start : start + _CHAT_ID_QUERY_CHUNK])))
            found.update(row[0] for row in rows.all())
    return found
