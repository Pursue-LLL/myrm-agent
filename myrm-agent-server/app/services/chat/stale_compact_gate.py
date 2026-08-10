"""Pre-reply stale session compaction gate.

Runs before a new user turn when a chat has been idle long enough that carrying
full stale history into the first LLM call is wasteful. Reuses ``compact_chat``;
does not implement a separate summarize pipeline.

[INPUT]
- app.services.agent.profile.profile_resolver::AgentProfileResolver.resolve (POS: engine_params SSOT)
- app.core.channel_bridge.config_loader::load_user_configs (POS: model window for idle floor)
- app.services.chat.compact_service::compact_chat (POS: lossless compaction SSOT; honors anti-thrash via harness guard; idle path receives request-level ``request_tokens_for_guard``)
- app.services.chat.compact_service::estimate_idle_compact_request_tokens (POS: idle gate request-level token estimate incl. compacted_summary)
- app.services.chat.compact_service::is_compaction_failure_cooldown_active (POS: post-failure cooldown guard)

[OUTPUT]
- parse_idle_compact_after_seconds: engine_params → seconds (0 = disabled)
- resolve_idle_compact_after_seconds: profile + request merge → seconds
- maybe_compact_stale_chat_before_turn: best-effort pre-reply compaction
- run_pre_reply_stale_compact_gate: Web/Channel entry with DB session (optional `on_before_compact` for Web SSE active)
- ModelWindowUnavailableError: fail-closed signal when model window cannot be resolved

[POS]
Server product-layer timing gate (Hermes ``idle_compact_after_seconds`` semantics).
Configured via Agent Profile ``engine_params.idle_compact_after_seconds`` (default 0).
Complements harness idle worker post-turn compaction — this covers resume-before-reply.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import replace
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Chat, Message
from app.services.chat.compact_service import (
    CompactResult,
    compact_chat,
    estimate_idle_compact_request_tokens,
    is_compaction_failure_cooldown_active,
    resolve_idle_compact_token_floor,
)

logger = logging.getLogger(__name__)


class ModelWindowUnavailableError(Exception):
    """User model window could not be loaded for idle compact floor evaluation."""


def _ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def parse_idle_compact_after_seconds(
    engine_params: dict[str, object] | None,
) -> int:
    """Return idle compact threshold seconds from engine_params (0 = disabled)."""
    if not engine_params:
        return 0
    raw = engine_params.get("idle_compact_after_seconds")
    if raw is None:
        return 0
    try:
        return max(0, int(raw))
    except (TypeError, ValueError):
        return 0


async def resolve_idle_compact_after_seconds(
    agent_id: str | None,
    request_engine_params: dict[str, object] | None = None,
) -> int:
    """Resolve idle compact seconds from agent profile + per-request engine_params."""
    engine_params: dict[str, object] | None = None
    if agent_id:
        from app.services.agent.profile.profile_resolver import get_agent_profile_resolver

        resolved = await get_agent_profile_resolver().resolve(agent_id)
        engine_params = resolved.engine_params
    if request_engine_params:
        engine_params = {**(engine_params or {}), **request_engine_params}
    return parse_idle_compact_after_seconds(engine_params)


async def _load_last_message_at(db: AsyncSession, chat_id: str) -> datetime | None:
    row = await db.execute(
        select(func.max(Message.created_at)).where(Message.chat_id == chat_id)
    )
    last_message_at = row.scalar_one_or_none()
    if last_message_at is None:
        return None
    return _ensure_utc(last_message_at)


async def _resolve_max_context_tokens() -> int | None:
    try:
        from app.core.channel_bridge.config_loader import load_user_configs

        configs = await load_user_configs()
        window = configs.model_cfg.max_context_tokens
        if window is None or window <= 0:
            return None
        return window
    except Exception as exc:
        logger.warning(
            "Idle compact gate: model window unavailable, skipping compact (fail-closed): %s",
            exc,
        )
        raise ModelWindowUnavailableError(str(exc)) from exc


async def maybe_compact_stale_chat_before_turn(
    db: AsyncSession,
    chat_id: str,
    *,
    idle_after_seconds: int,
    max_context_tokens: int | None = None,
    agent_id: str | None = None,
    on_before_compact: Callable[[], Awaitable[None]] | None = None,
) -> CompactResult:
    """Compact idle stale context before the next agent turn when configured."""
    if idle_after_seconds <= 0:
        return CompactResult(compacted=False, reason="idle_compact_disabled")

    chat_exists = await db.execute(select(Chat.id).where(Chat.id == chat_id))
    if chat_exists.scalar_one_or_none() is None:
        return CompactResult(compacted=False, reason="chat_not_found")

    last_message_at = await _load_last_message_at(db, chat_id)
    if last_message_at is None:
        return CompactResult(compacted=False, reason="no_messages")

    idle_seconds = (datetime.now(UTC) - last_message_at).total_seconds()
    if idle_seconds < idle_after_seconds:
        return CompactResult(
            compacted=False,
            reason=f"idle_below_threshold ({idle_seconds:.0f}s < {idle_after_seconds}s)",
        )

    cooldown_active, cooldown_error = await is_compaction_failure_cooldown_active(
        db, chat_id
    )
    if cooldown_active:
        return CompactResult(
            compacted=False,
            reason=f"compression_failure_cooldown_active ({cooldown_error or 'recent failure'})",
        )

    estimated_tokens, message_count = await estimate_idle_compact_request_tokens(
        db,
        chat_id,
        agent_id=agent_id,
    )

    model_window = max_context_tokens
    if model_window is None:
        try:
            model_window = await _resolve_max_context_tokens()
        except ModelWindowUnavailableError:
            return CompactResult(
                compacted=False,
                original_tokens=estimated_tokens,
                message_count=message_count,
                reason="model_window_unavailable_fail_closed",
            )
    if model_window is None:
        logger.warning(
            "Idle compact gate: model window unset after resolve, skipping compact (fail-closed)",
        )
        return CompactResult(
            compacted=False,
            original_tokens=estimated_tokens,
            message_count=message_count,
            reason="model_window_unavailable_fail_closed",
        )
    token_floor = resolve_idle_compact_token_floor(max_context_tokens=model_window)
    if estimated_tokens <= token_floor:
        return CompactResult(
            compacted=False,
            original_tokens=estimated_tokens,
            message_count=message_count,
            reason=f"context_below_floor ({estimated_tokens} <= {token_floor})",
        )

    if on_before_compact is not None:
        await on_before_compact()

    result = await compact_chat(
        db,
        chat_id,
        for_idle_stale=True,
        request_tokens_for_guard=estimated_tokens,
    )
    result = replace(result, attempted=True)
    if result.compacted:
        logger.info(
            "Pre-reply stale compact for chat %s after %.0fs idle (~%d tokens, saved ~%d)",
            chat_id,
            idle_seconds,
            estimated_tokens,
            result.tokens_saved,
        )
    else:
        logger.debug(
            "Pre-reply stale compact skipped for chat %s: %s",
            chat_id,
            result.reason,
        )
    return result


async def run_pre_reply_stale_compact_gate(
    chat_id: str,
    *,
    agent_id: str | None,
    request_engine_params: dict[str, object] | None = None,
    on_before_compact: Callable[[], Awaitable[None]] | None = None,
) -> CompactResult:
    """Run stale compact gate inside a DB session (Web + Channel SSOT)."""
    idle_after = await resolve_idle_compact_after_seconds(
        agent_id, request_engine_params
    )
    from app.database.connection import get_session

    async with get_session() as db:
        return await maybe_compact_stale_chat_before_turn(
            db,
            chat_id,
            idle_after_seconds=idle_after,
            on_before_compact=on_before_compact,
            agent_id=agent_id,
        )
