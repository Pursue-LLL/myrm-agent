"""Idle compaction token estimates and floors.

[INPUT]
- compact.message_io::load_chat, load_compactable_messages (POS: incremental tail slice)
- compact._constants::idle/overhead token constants (POS: floor + overhead heuristics)
- app.services.agent.profile.profile_resolver (POS: agent system prompt + tool/MCP overhead)

[OUTPUT]
- estimate_idle_compact_request_tokens: request-level tokens for idle gate floor
- resolve_idle_compact_token_floor: Hermes post-compaction target floor
- resolve_min_messages_to_compact: manual /compact min message guard

[POS]
Idle gate token accounting; separates Hermes idle predicate from manual compact guards.
"""

from __future__ import annotations

from myrm_agent_harness.utils.text_utils import get_token_count
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.chat.compact._constants import (
    DEFAULT_TOOL_SCHEMA_TOKEN_RESERVE,
    IDLE_SUMMARY_TARGET_RATIO,
    MAX_TOOL_OVERHEAD_TOKENS,
    MIN_INCREMENTAL_MESSAGES_TO_COMPACT,
    MIN_MESSAGES_TO_COMPACT,
    TOOL_OVERHEAD_TOKENS_PER_BUILTIN,
)
from app.services.chat.compact.message_io import (
    db_messages_to_langchain,
    load_chat,
    load_compactable_messages,
)


def resolve_min_messages_to_compact(*, compacted_summary: str | None) -> int:
    """Return minimum compactable messages (incremental merge allows fewer tail messages)."""
    if compacted_summary:
        return MIN_INCREMENTAL_MESSAGES_TO_COMPACT
    return MIN_MESSAGES_TO_COMPACT


async def estimate_compactable_context_tokens(
    db: AsyncSession,
    chat_id: str,
) -> tuple[int, int]:
    """Estimate token count for the incremental compactable message slice."""
    from myrm_agent_harness.utils.token_estimation import estimate_messages_tokens

    chat = await load_chat(db, chat_id)
    if chat is None:
        return 0, 0

    db_messages = await load_compactable_messages(db, chat)
    if not db_messages:
        return 0, 0

    return estimate_messages_tokens(db_messages_to_langchain(db_messages)), len(
        db_messages
    )


async def estimate_idle_compact_request_tokens(
    db: AsyncSession,
    chat_id: str,
    *,
    agent_id: str | None = None,
) -> tuple[int, int]:
    """Estimate request-level tokens for idle gate floor (summary + messages + agent overhead)."""
    message_tokens, message_count = await estimate_compactable_context_tokens(
        db, chat_id
    )
    summary_tokens = 0
    chat = await load_chat(db, chat_id)
    if chat is not None and chat.compacted_summary:
        summary_tokens = get_token_count(chat.compacted_summary)
    overhead = await estimate_idle_compact_request_overhead(agent_id)
    return message_tokens + summary_tokens + overhead, message_count


async def estimate_idle_compact_request_overhead(agent_id: str | None) -> int:
    overhead = DEFAULT_TOOL_SCHEMA_TOKEN_RESERVE
    if not agent_id:
        return overhead

    from app.services.agent.profile.profile_resolver import get_agent_profile_resolver

    resolved = await get_agent_profile_resolver().resolve(agent_id)
    if resolved is not None:
        if resolved.system_prompt:
            overhead += get_token_count(resolved.system_prompt)
        tool_count = len(resolved.enabled_builtin_tools)
        overhead += min(
            tool_count * TOOL_OVERHEAD_TOKENS_PER_BUILTIN, MAX_TOOL_OVERHEAD_TOKENS
        )
        overhead += min(len(resolved.mcp_ids) * 600, 12_000)
    return overhead


def resolve_idle_compact_token_floor(
    max_context_tokens: int | None = None,
) -> int:
    """Post-compaction target floor (Hermes threshold × summary_target_ratio semantics)."""
    from myrm_agent_harness.agent.context_management.infra.schemas import (
        DEFAULT_CONTEXT_CONFIG,
        ContextConfig,
    )

    window = max_context_tokens or DEFAULT_CONTEXT_CONFIG.max_context_tokens
    cfg = ContextConfig(max_context_tokens=window)
    return int(cfg.compress_threshold * IDLE_SUMMARY_TARGET_RATIO)
