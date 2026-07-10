"""Background hook: archive SessionNotes into the wiki vault after persistence.

[INPUT]
- app.services.chat.chat_crud::ChatService (POS: chat CRUD operations)
- app.services.wiki.vault_service::get_wiki_archiver (POS: shared wiki archiver accessor)
- app.services.wiki.memory_to_wiki::MemoryToWikiArchiver (POS: Memory→Wiki automatic archiving service)

[OUTPUT]
- archive_session_notes_to_wiki(): persist SessionNotes into canonical wiki vault

[POS]
Server-side bridge from context compression SessionNotes persistence to wiki raw ingestion.
"""

from __future__ import annotations

import logging

from langchain_core.language_models import BaseChatModel

from app.services.chat.chat_service import ChatService
from app.services.wiki.memory_to_wiki import MemoryToWikiArchiver
from app.services.wiki.vault_service import get_wiki_archiver

logger = logging.getLogger(__name__)


async def archive_session_notes_to_wiki(
    chat_id: str,
    notes_json: str,
    *,
    llm: BaseChatModel,
) -> None:
    """Archive structured session notes to wiki when turn and content thresholds are met."""
    try:
        turn_count = MemoryToWikiArchiver.estimate_turn_count_from_notes(notes_json)
        if turn_count <= 0:
            turn_count = await ChatService.count_messages(chat_id)

        archiver = get_wiki_archiver(llm)
        archived = await archiver.archive_memory(
            notes_json,
            conversation_turns=turn_count,
            chat_id=chat_id,
        )
        if archived:
            logger.info(
                "Session notes archived to wiki for chat_id=%s turns=%d",
                chat_id,
                turn_count,
            )
    except Exception as exc:
        logger.warning("Wiki session-notes archive skipped for chat_id=%s: %s", chat_id, exc)
