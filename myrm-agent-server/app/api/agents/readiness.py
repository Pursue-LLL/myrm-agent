"""Agent Readiness API — per-agent configuration dry-run.

[INPUT]
- Agent ID (path param)

[OUTPUT]
- AgentReadinessReport: overall_level, items[], agent_id, checked_at

[POS]
Server-side endpoint that resolves per-agent readiness by checking 6 dimensions
(model / mcp / skills / tools / search / deployment). Returns structured report
with ready / warning / blocked levels and settings deep-link paths.
Zero LLM calls — pure deterministic + config checks.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter

from app.core.utils.response_utils import success_response
from app.services.agent.readiness import get_readiness_resolver

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/{agent_id}/readiness")
async def get_agent_readiness(agent_id: str) -> dict[str, object]:
    """Check agent configuration readiness before execution.

    Returns a structured report with overall level (ready/warning/blocked),
    per-dimension items with reasons and settings deep-links.
    """
    resolver = get_readiness_resolver()
    report = await resolver.resolve(agent_id)
    return success_response(data=report.to_dict())


@router.post("/{agent_id}/readiness/invalidate")
async def invalidate_agent_readiness(agent_id: str) -> dict[str, object]:
    """Invalidate cached readiness for a specific agent.

    Called by frontend after Settings save to force re-evaluation.
    """
    resolver = get_readiness_resolver()
    resolver.invalidate(agent_id)
    return success_response(data={"invalidated": True, "agent_id": agent_id})
