"""Callbacks for General Agent

Contains persistence and notification callbacks separated from the main agent logic.

@input: 依赖 app.services.chat.compact_service (POS: 上下文压缩持久化服务)
@output: make_commitment_extraction_callback / make_loaded_skills_persist_callback / make_summary_persist_with_wiki_archive / make_notes_persist / make_notes_load / make_skill_review_callback
@pos: Agent 会话清理与持久化回调工厂
"""

import logging
from collections.abc import Awaitable, Callable, Sequence
from typing import cast

from langchain_core.language_models import BaseChatModel

logger = logging.getLogger(__name__)


def get_persist_compaction() -> Callable[[str, object, str, int], Awaitable[None]]:
    """Lazy-load persist_compaction to avoid circular imports at module level."""
    from app.services.chat.compact_service import persist_compaction

    return cast(Callable[[str, object, str, int], Awaitable[None]], persist_compaction)


def make_notes_persist(chat_id: str) -> Callable[[str], Awaitable[None]]:
    """Create a Session Notes persist callback bound to a specific chat_id."""

    async def _persist(notes_json: str) -> None:
        from sqlalchemy import update

        from app.database.connection import get_session
        from app.database.models import Chat

        async with get_session() as db:
            await db.execute(update(Chat).where(Chat.id == chat_id).values(session_notes_json=notes_json))
            await db.commit()
            logger.info("💾 [SessionNotes] Persisted to DB: chat_id=%s", chat_id)

    return _persist


def make_summary_persist_with_wiki_archive(
    *,
    enable_wiki: bool,
    wiki_archive_llm: BaseChatModel | None,
) -> Callable[[str, object, str, int], Awaitable[None]]:
    """Wrap compaction persist to archive SessionNotes into wiki after context compression."""
    base_persist = get_persist_compaction()

    async def _persist_with_wiki(
        chat_id: str,
        summary: object,
        before_message_id: str,
        tokens_saved: int,
    ) -> None:
        await base_persist(chat_id, summary, before_message_id, tokens_saved)
        if not enable_wiki or wiki_archive_llm is None:
            return

        import asyncio

        from myrm_agent_harness.api import track_background_task

        from app.services.wiki.wiki_archive_hook import archive_session_notes_to_wiki

        notes_loader = make_notes_load(chat_id)

        async def _archive_after_compact() -> None:
            notes_json = await notes_loader()
            if not notes_json:
                return
            await archive_session_notes_to_wiki(chat_id, notes_json, llm=wiki_archive_llm)

        task = asyncio.create_task(_archive_after_compact())
        track_background_task(task)

    return _persist_with_wiki


def make_notes_load(chat_id: str) -> Callable[[], Awaitable[str | None]]:
    """Create a Session Notes load callback bound to a specific chat_id."""

    async def _load() -> str | None:
        from sqlalchemy import select

        from app.database.connection import get_session
        from app.database.models import Chat

        async with get_session() as db:
            result = await db.execute(select(Chat.session_notes_json).where(Chat.id == chat_id))
            val = result.scalar_one_or_none()
            if val is None or isinstance(val, str):
                return val
            return None

    return _load


def make_loaded_skills_persist_callback() -> Callable[[list[str], str | None], Awaitable[None]]:
    """Persist loaded skill names to Chat.session_loaded_skill_names at turn end."""

    async def _persist(skill_names: list[str], chat_id: str | None) -> None:
        if not chat_id:
            return
        from app.services.chat.chat_service import ChatService

        await ChatService.update_chat_fields(chat_id, {"session_loaded_skill_names": skill_names})
        logger.info(
            "Persisted session_loaded_skill_names: chat_id=%s count=%d",
            chat_id,
            len(skill_names),
        )

    return _persist


def make_skill_review_callback() -> Callable[[dict[str, object]], None]:
    """Create the on_skill_review_ready callback for the GeneralAgent.

    This callback is invoked by the Harness layer after a background skill review
    completes. It delegates the result into the unified skill growth lifecycle
    without blocking the main agent response.
    """

    def _notify(result: dict[str, object]) -> None:
        import asyncio

        asyncio.create_task(_notify_async(result))

    async def _notify_async(result: dict[str, object]) -> None:
        from app.services.skills.growth.lifecycle import process_skill_review_result

        try:
            await process_skill_review_result(result)
        except Exception:
            logger.error("Failed to process skill extraction", exc_info=True)

    return _notify


def make_commitment_extraction_callback(
    agent_id: str,
    user_id: str,
    channel: str = "web",
    llm_func: Callable[[str, str], Awaitable[str]] | None = None,
) -> Callable[[Sequence[dict[str, str]], str | None], Awaitable[None]]:
    """Create the on_session_cleanup callback for commitment extraction.

    Invoked by the Harness layer after session cleanup. Extracts implicit
    commitments from the conversation and persists them via SQLite store.
    """

    async def _extract(messages: Sequence[dict[str, str]], chat_id: str | None) -> None:
        if llm_func is None:
            return
        try:
            from app.core.channel_bridge.config_loader import load_user_configs
            from app.core.memory.proactive.extraction_hook import run_commitment_extraction
            from app.core.memory.proactive.settings import resolve_memory_enabled

            timezone = "UTC"
            try:
                user_cfgs = await load_user_configs()
                memory_settings = user_cfgs.personal_settings_dict or {}
                if not resolve_memory_enabled(memory_settings):
                    return
                tz_raw = memory_settings.get("timezone")
                if isinstance(tz_raw, str) and tz_raw.strip():
                    timezone = tz_raw.strip()
            except Exception:
                logger.debug("Using UTC for proactive extraction; user timezone unavailable")

            await run_commitment_extraction(
                messages,
                llm_func,
                agent_id=agent_id,
                user_id=user_id,
                channel=channel,
                source_chat_id=chat_id,
                timezone=timezone,
            )
        except Exception as e:
            logger.warning("Commitment extraction skipped: %s", e)

    return _extract
