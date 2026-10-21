"""Bind approved competitor skills to a target agent profile.

[INPUT]
app.services.agent.agent_service::AgentService (POS: Agent CRUD)

[OUTPUT]
bind_local_skill_names_to_agent: merge skill directory names into Agent profile skills list

[POS]
Post-approve hook for competitor skill migration review queue.
"""

from __future__ import annotations

import logging

from app.database.dto import AgentUpdate
from app.services.agent.agent_service import AgentService

logger = logging.getLogger(__name__)


async def bind_local_skill_names_to_agent(agent_id: str, skill_names: list[str]) -> int:
    """Append local skill folder names to the target agent skills list."""

    cleaned = [name.strip() for name in skill_names if name.strip()]
    if not cleaned:
        return 0

    agent = await AgentService.get_agent_by_id(agent_id)
    if agent is None:
        logger.warning("Cannot bind skills: target agent %s not found", agent_id)
        return 0

    existing = list(agent.skills or [])
    merged: list[str] = []
    seen: set[str] = set()
    for skill_id in [*existing, *cleaned]:
        if skill_id in seen:
            continue
        seen.add(skill_id)
        merged.append(skill_id)

    if merged == existing:
        return 0

    outcome = await AgentService.update_agent(agent_id, AgentUpdate(skill_ids=merged))
    if outcome is None:
        return 0
    return len(merged) - len(existing)
