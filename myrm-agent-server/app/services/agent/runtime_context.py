"""Shared agent runtime context for process_stream / finalize_agent_session.

[INPUT]
- app.core.skills.disabled_skill_roots::collect_disabled_skill_roots (POS: disabled skill roots)
- app.services.agent.execution_cache.types::ExecutionMode (POS: pooled vs ephemeral)

[OUTPUT]
- build_agent_runtime_context: merge execution_mode + disabled_skill_roots into a context dict

[POS]
Business-layer helper so every agent entrypoint (Web, IM, Cron, Kanban, eval, wakeup)
passes the same runtime context keys to the harness, including disabled skill path filtering.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.services.agent.execution_cache.types import ExecutionMode

if TYPE_CHECKING:
    from app.services.agent.params.models import AgentRequest

logger = logging.getLogger(__name__)


def resolve_stream_execution_mode() -> ExecutionMode:
    """POOLED by default; SHPOIB private backends force ephemeral to avoid stale security."""
    import os

    if os.environ.get("MYRM_E2E_FORCE_EPHEMERAL", "").strip() == "1":
        return ExecutionMode.EPHEMERAL
    return ExecutionMode.POOLED


def prefer_direct_agent_stream(request: AgentRequest) -> AgentRequest:
    """SHPOIB Chrome E2E: workspace multiplex is unreliable across isolated backends."""
    import os

    if os.environ.get("MYRM_E2E_SHPOIB", "").strip() != "1" or not request.multiplexed:
        return request
    return request.model_copy(update={"multiplexed": False})


async def build_agent_runtime_context(
    *,
    execution_mode: ExecutionMode,
    base: dict[str, object] | None = None,
) -> dict[str, object]:
    """Build RunnableConfig context with execution mode and disabled skill roots."""
    ctx: dict[str, object] = dict(base or {})
    ctx["execution_mode"] = execution_mode

    try:
        from app.core.skills.disabled_skill_roots import collect_disabled_skill_roots

        ctx["disabled_skill_roots"] = await collect_disabled_skill_roots()
    except Exception as exc:
        logger.warning("Failed to collect disabled_skill_roots: %s", exc)
        ctx.setdefault("disabled_skill_roots", [])

    return ctx
