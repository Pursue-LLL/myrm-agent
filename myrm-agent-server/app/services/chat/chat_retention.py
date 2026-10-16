"""Time-based permanent deletion of chats: expired trash and idle incognito sessions.

[INPUT]
- app.database.repositories.uow::UnitOfWork (POS: transactional repository access)
- app.database.repositories.chat_repo::ChatRepository (POS: chat persistence)
- app.services.chat.chat_service::ChatService (POS: chat lifecycle facade that owns the full deletion teardown)
- app.services.agent.gateway::get_agent_gateway (POS: which conversations have a turn in flight)

[OUTPUT]
- purge_expired_trash: permanently delete chats that stayed in the trash past the retention window
- purge_idle_incognito_chats: permanently delete idle web incognito chats that have no turn in flight

[POS]
Retention policy for the scheduler. It only decides which chats are due and delegates the deletion to
``ChatService``, so an automatic purge tears down exactly what a manual one does.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.database.models import Chat
from app.database.repositories.chat_repo import ChatRepository
from app.database.repositories.uow import UnitOfWork
from app.services.agent.gateway import get_agent_gateway

from .chat_service import ChatService

logger = logging.getLogger(__name__)

TRASH_RETENTION = timedelta(days=30)
INCOGNITO_MAX_IDLE = timedelta(hours=1)


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
    skipped and picked up by a later run.
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
    deleted = 0
    for chat_id in chat_ids:
        if chat_id in gateway.active_session_ids():
            continue
        try:
            # Permanent deletion only accepts trashed chats; its teardown already covers what a soft delete stops.
            async with UnitOfWork() as uow:
                await uow.chat_repo.soft_delete_chat(chat_id)
            if await ChatService.permanently_delete_chat(chat_id):
                deleted += 1
        except Exception as exc:
            logger.warning("Incognito chat auto-purge failed (chat=%s): %s", chat_id, exc)
    if deleted:
        logger.info("Incognito chat auto-purge: %d expired incognito chats permanently deleted", deleted)
    return deleted
