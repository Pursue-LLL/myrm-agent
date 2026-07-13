"""Channel chat history persistence and title generation.

[INPUT]
- app.services.chat.chat_service::ChatService (POS: Chat history persistence)

[OUTPUT]
- build_chat_history_with_metadata, persist_and_load_history, load_history_without_persist
- persist_assistant_message, generate_channel_title

[POS]
Channel executor 辅助：入站/出站消息持久化与频道标题生成。
"""

from __future__ import annotations

import logging
from datetime import datetime
from datetime import timezone as tz_module
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.chat.chat_service import ChannelHistoryEntry

logger = logging.getLogger(__name__)


def build_chat_history_with_metadata(
    entries: list[ChannelHistoryEntry],
) -> list[list[str | object]]:
    """Convert structured history entries to framework chat_history format."""
    history: list[list[str | object]] = []
    for entry in entries:
        if entry.role == "human":
            history.append(["human", entry.content, {"ts": entry.created_at.isoformat()}])
        else:
            history.append(["assistant", entry.content])
    return history


async def persist_and_load_history(
    channel_session_key: str,
    source: str,
    content: str,
    sent_at: datetime,
    sent_timezone: str,
    agent_id: str | None = None,
) -> tuple[str, list[ChannelHistoryEntry]]:
    """Persist the user message and load chat history in a single DB session."""
    from app.database.connection import get_session
    from app.services.chat.chat_service import ChatService

    async with get_session() as session:
        chat = await ChatService.get_or_create_channel_chat(
            channel_session_key,
            source,
            agent_id=agent_id,
        )
        await ChatService.append_message(chat.id, "user", content, sent_at, sent_timezone)
        history = await ChatService.load_channel_history(chat.id, api_key=None)
        await session.commit()
        logger.warning(
            "Channel chat persisted: chat_id=%s, history_len=%d",
            chat.id,
            len(history),
        )
        return chat.id, history


async def load_history_without_persist(
    channel_session_key: str,
) -> tuple[str, list[ChannelHistoryEntry]]:
    """Load chat history without persisting any new message (for resume operations)."""
    from app.database.connection import get_session
    from app.services.chat.chat_service import ChatService

    async with get_session() as _session:
        chat = await ChatService.get_channel_chat_by_key(channel_session_key)
        if not chat:
            logger.warning(
                "Resume attempted but no chat found for session_key=%s",
                channel_session_key,
            )
            return "", []

        history = await ChatService.load_channel_history(chat.id, api_key=None)
        logger.warning(
            "Resume: loaded history for chat_id=%s, history_len=%d",
            chat.id,
            len(history),
        )
        return chat.id, history


async def persist_assistant_message(
    chat_id: str,
    content: str,
    timezone: str | None = None,
    extra_data: dict[str, object] | None = None,
) -> None:
    """Persist the assistant's response after Agent completes."""
    from app.database.connection import get_session
    from app.services.chat.chat_service import ChatService

    async with get_session() as session:
        sent_at = datetime.now(tz=tz_module.utc)
        sent_timezone = timezone or "UTC"
        await ChatService.append_message(
            chat_id, "assistant", content, sent_at, sent_timezone, extra_data=extra_data,
        )
        await session.commit()


async def generate_channel_title(
    chat_id: str,
    first_message: str,
    lite_model_cfg: object | None,
) -> None:
    """Generate an LLM-powered title for a new channel chat (fire-and-forget)."""
    from app.database.connection import get_session
    from app.database.dto import _TitleModelConfig
    from app.services.chat.chat_service import ChatService

    try:
        title_model: _TitleModelConfig | None = None
        if lite_model_cfg is not None:
            from app.core.types import ModelConfig

            if isinstance(lite_model_cfg, ModelConfig):
                title_model = _TitleModelConfig.model_validate(
                    {
                        "model": lite_model_cfg.model,
                        "apiKey": lite_model_cfg.api_key,
                        "baseUrl": lite_model_cfg.base_url,
                    }
                )

        if title_model:
            title = await ChatService._call_llm_for_title(first_message[:200], title_model)
        else:
            title = ChatService._generate_fallback_title(first_message)

        async with get_session() as _session:
            await ChatService.update_chat_title(chat_id, title)
    except Exception:
        logger.warning("Failed to generate channel chat title for %s", chat_id)
