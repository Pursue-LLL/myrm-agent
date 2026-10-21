"""Finalize GeneralAgent sessions for pooled vs ephemeral execution modes.

[INPUT]
- execution_cache.registry::get_execution_cache (POS: chat 级 BuiltExecutionUnit 池)
- execution_cache.unit_ops::capture_built_unit (POS: wrapper ↔ unit 捕获)

[OUTPUT]
- resolve_execution_mode, finalize_agent_session

[POS]
execution_cache 会话收尾。按 execution_mode 决定 release 或 refresh 缓存单元。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.services.agent.execution_cache.fingerprint import build_execution_scope_key
from app.services.agent.execution_cache.registry import get_execution_cache
from app.services.agent.execution_cache.types import ExecutionMode
from app.services.agent.execution_cache.unit_ops import capture_built_unit, detach_wrapper_refs

if TYPE_CHECKING:
    from app.ai_agents.general_agent.agent import GeneralAgent

logger = logging.getLogger(__name__)


def resolve_execution_mode(extra_context: dict[str, object] | None) -> ExecutionMode:
    if extra_context is None:
        return ExecutionMode.POOLED
    raw = extra_context.get("execution_mode")
    if raw == ExecutionMode.EPHEMERAL or raw == "ephemeral":
        return ExecutionMode.EPHEMERAL
    return ExecutionMode.POOLED


async def finalize_agent_session(
    agent: GeneralAgent,
    *,
    chat_id: str | None,
    agent_id: str | None,
    extra_context: dict[str, object] | None = None,
) -> None:
    """Release pooled resources or fully close an ephemeral agent run."""
    mode = resolve_execution_mode(extra_context)
    if mode == ExecutionMode.POOLED:
        scope_key = build_execution_scope_key(chat_id, agent_id)
        try:
            await agent.release_pooled_session()
        except Exception:
            logger.warning("release_pooled_session failed chat=%s", chat_id, exc_info=True)
        if scope_key is not None and agent.agent is not None:
            try:
                await get_execution_cache().refresh_unit(
                    scope_key,
                    capture_built_unit(agent, agent.agent),
                )
            except Exception:
                logger.warning("execution_cache_refresh failed scope=%s", scope_key, exc_info=True)
        detach_wrapper_refs(agent)
        if scope_key is not None:
            try:
                await get_execution_cache().release(scope_key)
            except Exception:
                logger.warning("execution_cache_release failed scope=%s", scope_key, exc_info=True)
        return

    await agent.close()
