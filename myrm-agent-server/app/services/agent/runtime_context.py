"""Shared agent runtime context for process_stream / finalize_agent_session.

[INPUT]
- app.core.skills.gates.disabled_skill_roots::collect_disabled_skill_roots (POS: disabled skill roots)
- app.services.agent.execution_cache.types::ExecutionMode (POS: pooled vs ephemeral)
- app.ai_agents.general_agent.tools::ensure_tool_layer_bootstrap (POS: lazy server-tool registration)

[OUTPUT]
- SINGLE_TENANT_USER_ID: the one user id every single-tenant server run is bound to
- build_agent_runtime_context: merge user_id + execution_mode + disabled_skill_roots into a context dict

[POS]
Business-layer helper so every agent entrypoint (Web, IM, Cron, Kanban, Eval, Wakeup,
Goal stream, timeout auto-resume, offline recovery, OpenAI-compatible API, voice)
passes the same runtime context keys to the harness, including disabled skill path filtering
and the user_id that harness skill tools (skill_manage, skill_market install/uninstall) require.
It also awaits the lazy server-tool bootstrap so no entrypoint can build an agent against a
half-registered tool-layer registry.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from app.services.agent.execution_cache.types import ExecutionMode

if TYPE_CHECKING:
    from app.services.agent.params.models import AgentRequest

logger = logging.getLogger(__name__)

# Single-tenant SSOT: matches the cron REST ``USER_ID`` and the agent factory's fallback id.
SINGLE_TENANT_USER_ID = "default"


def resolve_stream_execution_mode() -> ExecutionMode:
    """POOLED by default for agent streams."""
    return ExecutionMode.POOLED


def prefer_direct_agent_stream(request: AgentRequest) -> AgentRequest:
    """Answer this turn on the POST response body when the instance cannot multiplex.

    An isolated per-lane backend does not serve the shared workspace stream, so a
    multiplexed request would otherwise hand the turn to a stream nobody reads.
    """
    from app.platform_utils.deployment_capabilities import get_deployment_capabilities

    if get_deployment_capabilities().supports_multiplexed_stream or not request.multiplexed:
        return request
    return request.model_copy(update={"multiplexed": False})


async def build_agent_runtime_context(
    *,
    execution_mode: ExecutionMode,
    base: dict[str, object] | None = None,
) -> dict[str, object]:
    """Build RunnableConfig context with user id, execution mode and disabled skill roots."""
    # HTTP startup no longer imports the full agent tool chain; every entrypoint reaches
    # this helper, so awaiting the idempotent bootstrap guarantees a complete registry
    # before the first turn (the startup preload usually finishes first).
    from app.ai_agents.general_agent.tools import ensure_tool_layer_bootstrap

    await asyncio.to_thread(ensure_tool_layer_bootstrap)

    ctx: dict[str, object] = dict(base or {})
    ctx.setdefault("user_id", SINGLE_TENANT_USER_ID)
    ctx["execution_mode"] = execution_mode

    try:
        from app.core.skills.gates.disabled_skill_roots import (
            collect_disabled_skill_roots,
        )

        ctx["disabled_skill_roots"] = await collect_disabled_skill_roots()
    except Exception as exc:
        logger.warning("Failed to collect disabled_skill_roots: %s", exc)
        ctx.setdefault("disabled_skill_roots", [])

    return ctx
