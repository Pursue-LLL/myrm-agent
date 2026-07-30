"""Resolve GeneralAgentParams for turn prewarm (no user message required).

[INPUT]
- app.services.agent.params.converter::convert_to_general_agent_params (POS: param builder)
- app.services.agent.params.models::AgentRequest (POS: request DTO)

[OUTPUT]
- resolve_prewarm_agent_params() (POS: prewarm param factory)

[POSITION] app.services.agent.execution_cache.prewarm — param resolver for speculative warm-up.
"""

from __future__ import annotations

import uuid

from app.ai_agents import GeneralAgentParams
from app.services.agent.params.converter import convert_to_general_agent_params
from app.services.agent.params.models import AgentRequest


async def resolve_prewarm_agent_params(
    *,
    chat_id: str,
    agent_id: str | None,
    action_mode: str = "agent",
    incognito_mode: bool = False,
) -> GeneralAgentParams:
    """Build runtime params matching a would-be stream turn (empty query)."""
    request = AgentRequest(
        message_id=f"prewarm-{uuid.uuid4().hex[:12]}",
        chat_id=chat_id,
        agent_id=agent_id,
        query="",
        action_mode=action_mode,
        incognito_mode=incognito_mode,
    )
    params, _routing, _warnings, _archive = await convert_to_general_agent_params(
        request,
        [],
        http_request=None,
    )
    return params
