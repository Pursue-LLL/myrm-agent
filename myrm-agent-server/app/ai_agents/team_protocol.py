"""Team Leader Operating Protocol — prompt injection for team-type agents.

[INPUT]
- myrm_agent_harness.backends.profiles.types::AgentProfile (POS: Agent Profile data)
- app.services.agent.agent_service::AgentService (POS: Agent CRUD)

[OUTPUT]
- build_leader_protocol_prompt(): Generate Leader Operating Protocol prompt with roster

[POS]
When agent_type='team', this module generates a Leader Operating Protocol
that is appended to the agent's system instructions. The protocol contains
a team roster (resolved from subagent_ids) and routing/coordination rules
so the LLM knows how to delegate work to team members via the subagent system.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

_LEADER_PROTOCOL_TEMPLATE = """\
<team_leader_protocol>
## Role
You are the **Leader** of this Agent Team. Your primary role is to coordinate \
team members to accomplish user requests efficiently.

## Team Roster
{roster}

## Operating Rules
1. **Analyze** the user's request and determine which team member(s) are best \
suited to handle it, based on their specialization and description.
2. **Delegate** tasks to the appropriate member(s) using the `delegate_task` or \
`delegate_parallel_tasks` tool. Provide clear, actionable instructions.
3. **Synthesize** results from member(s) into a coherent response for the user.
4. **Handle directly** simple requests that don't require specialized expertise \
(e.g. greetings, clarifications, general knowledge).
5. When a task spans multiple specializations, break it down and delegate \
sub-parts to different members in parallel when possible.
6. If no member is suited for the task, handle it yourself using your own tools.

## Coordination Principles
- Prefer parallel delegation over sequential when sub-tasks are independent.
- Always attribute which member produced which part of the answer when combining results.
- If a member fails, try an alternative member or handle the task yourself.
</team_leader_protocol>"""


@dataclass(frozen=True, slots=True)
class RosterEntry:
    agent_id: str
    display_name: str
    description: str


async def _resolve_roster(subagent_ids: list[str]) -> list[RosterEntry]:
    """Resolve subagent_ids into roster entries with display names and descriptions."""
    if not subagent_ids:
        return []

    import asyncio

    from app.services.agent.agent_service import AgentService

    async def _fetch_one(agent_id: str) -> RosterEntry | None:
        try:
            profile = await AgentService.get_agent_by_id(agent_id)
            if profile:
                return RosterEntry(
                    agent_id=agent_id,
                    display_name=profile.display_name or agent_id,
                    description=profile.description or "No description",
                )
            logger.warning("Team member '%s' not found, skipping", agent_id)
        except Exception as e:
            logger.warning("Failed to resolve team member '%s': %s", agent_id, e)
        return None

    results = await asyncio.gather(*[_fetch_one(aid) for aid in subagent_ids])
    return [r for r in results if r is not None]


def _format_roster(entries: list[RosterEntry]) -> str:
    if not entries:
        return "(No team members configured)"

    lines: list[str] = []
    for entry in entries:
        lines.append(
            f"- **{entry.display_name}** (`{entry.agent_id}`): {entry.description}"
        )
    return "\n".join(lines)


async def build_leader_protocol_prompt(
    subagent_ids: list[str],
) -> str:
    """Build the Leader Operating Protocol prompt for a team-type agent.

    Resolves subagent_ids into a roster with names/descriptions,
    then renders the protocol template.
    """
    roster_entries = await _resolve_roster(subagent_ids)
    roster_text = _format_roster(roster_entries)
    return _LEADER_PROTOCOL_TEMPLATE.format(roster=roster_text)
