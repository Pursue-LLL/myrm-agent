"""Retry memory extraction for one chat turn (GUI manual recovery).

[INPUT]
app.services.chat.chat_service::ChatService (POS: chat metadata)
app.services.context.context_assembly::ContextAssemblyService (POS: chat memory binding SSOT)
app.services.memory.resolve_chat_extraction_llm::resolve_chat_extraction_llm (POS: extraction LLM SSOT)
myrm_agent_harness.agent._internals.memory_extraction::auto_extract_memories (POS: harness extract)
app.ai_agents.extensions.extraction_lifecycle::make_extraction_lifecycle_observer (POS: ledger bridge)

[OUTPUT]
schedule_retry_chat_memory_extract: Fire-and-forget re-run of auto_extract for last user/assistant turn.
Returns `scheduled` or `already_in_flight` (in-process dedup via asyncio.Lock).

[POS]
Business-layer manual recovery when auto extract failed. Reuses harness extract with factory-aligned
memory binding and extraction LLM — no new engine.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Literal

from myrm_agent_harness.utils.chat_utils import ChatHistoryReq

from app.database.dto import MessageDTO
from app.services.chat.chat_service import ChatService

logger = logging.getLogger(__name__)

RetryScheduleStatus = Literal["scheduled", "already_in_flight"]

_in_flight_retries: set[str] = set()
_in_flight_lock = asyncio.Lock()


def _time_decay_half_life_days(memory_decay_profile: str | None) -> float:
    if memory_decay_profile == "permanent":
        return 3650.0
    if memory_decay_profile == "fast":
        return 7.0
    return 90.0


def _find_last_turn(
    messages: list[MessageDTO],
) -> tuple[MessageDTO, MessageDTO, ChatHistoryReq]:
    active = [message for message in messages if message.is_active]
    last_user_index = -1
    for index, message in enumerate(active):
        if message.role == "user":
            last_user_index = index

    if last_user_index < 0:
        raise ValueError("No user message found for memory retry")

    last_user = active[last_user_index]
    last_assistant = next(
        (
            message
            for message in active[last_user_index + 1 :]
            if message.role == "assistant"
        ),
        None,
    )
    if last_assistant is None:
        raise ValueError("No assistant reply found for memory retry")

    history: ChatHistoryReq = []
    for message in active[:last_user_index]:
        role = "human" if message.role == "user" else "assistant"
        history.append([role, message.content or ""])

    return last_user, last_assistant, history


async def _run_retry_extract(
    chat_id: str, query: str, history: ChatHistoryReq, assistant_reply: str
) -> None:
    try:
        from myrm_agent_harness.agent._internals.memory_extraction import (
            auto_extract_memories,
        )

        from app.ai_agents.extensions.extraction_lifecycle import (
            make_extraction_lifecycle_observer,
        )
        from app.core.memory.adapters.setup import (
            create_conflict_callback,
            create_memory_manager,
        )
        from app.services.agent.platform_config import require_platform_embedding_config
        from app.services.context.context_assembly import ContextAssemblyService
        from app.services.memory.resolve_chat_extraction_llm import (
            resolve_chat_extraction_llm,
        )

        binding_context = await ContextAssemblyService.resolve_binding_for_chat(chat_id)
        llm, extraction_llm = await resolve_chat_extraction_llm(chat_id)

        embedding_cfg = await require_platform_embedding_config()
        memory_manager = await create_memory_manager(
            binding_context.binding,
            embedding_cfg,
            approval_required=False,
            dedup_llm=extraction_llm,
            time_decay_half_life_days=_time_decay_half_life_days(
                binding_context.memory_decay_profile
            ),
            on_conflict=create_conflict_callback(agent_id=binding_context.agent_id),
        )

        await auto_extract_memories(
            query,
            history,
            memory_manager,
            llm,
            extraction_llm=extraction_llm,
            source_chat_id=chat_id,
            assistant_reply=assistant_reply,
            lifecycle_observer=make_extraction_lifecycle_observer(
                chat_id,
                source="manual_retry_extract",
                manual_retry=True,
            ),
        )
    except Exception as exc:
        logger.warning(
            "Manual memory extract retry failed for chat %s: %s", chat_id, exc
        )


async def schedule_retry_chat_memory_extract(chat_id: str) -> RetryScheduleStatus:
    """Schedule background retry for the latest active user/assistant turn."""
    resolved_chat_id = chat_id.strip()
    if not resolved_chat_id:
        raise ValueError("Chat id is required")

    async with _in_flight_lock:
        if resolved_chat_id in _in_flight_retries:
            logger.info(
                "Memory extract retry already in flight for chat %s", resolved_chat_id
            )
            return "already_in_flight"

    chat = await ChatService.get_chat_metadata(resolved_chat_id)
    if chat is None:
        raise ValueError("Chat not found")
    if chat.is_incognito:
        raise ValueError("Incognito chats do not support memory extraction retry")

    messages = await ChatService.get_all_messages(resolved_chat_id)
    if not messages:
        raise ValueError("Chat has no messages")

    last_user, last_assistant, history = _find_last_turn(messages)

    async with _in_flight_lock:
        if resolved_chat_id in _in_flight_retries:
            return "already_in_flight"
        _in_flight_retries.add(resolved_chat_id)

    async def _run_guarded() -> None:
        try:
            await _run_retry_extract(
                resolved_chat_id,
                last_user.content or "",
                history,
                last_assistant.content or "",
            )
        finally:
            _in_flight_retries.discard(resolved_chat_id)

    asyncio.create_task(_run_guarded())
    return "scheduled"
