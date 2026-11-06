"""Agent 路由命令与技能命令绑定。

[POS]
channel_bridge setup 子包的一部分；由 __init__.py 聚合导出。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.core.channel_bridge import channel_gateway

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from app.channels.routing.command_defs import CommandDef


def _build_agent_route_commands() -> tuple[CommandDef, ...]:
    """Build agent routing slash commands for this deployment.

    These are business-layer definitions (specific agent names/aliases)
    registered into the harness CommandRegistry at router init time.
    """
    from app.channels.routing.command_defs import (
        CommandDef,
        CommandKind,
    )

    _AGENT_ROUTES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
        ("claude", "Route message to Claude agent", ("cc",)),
        ("codex", "Route message to Codex agent", ("cx",)),
        ("cursor", "Route message to Cursor agent", ("cs",)),
        ("kimi", "Route message to Kimi agent", ("km",)),
        ("gemini", "Route message to Gemini agent", ("gm",)),
        ("openclaw", "Route message to OpenClaw agent", ("oc",)),
        ("opencode", "Route message to OpenCode agent", ("ocd",)),
    )

    return tuple(
        CommandDef(
            name=agent_id,
            description=description,
            kind=CommandKind.AGENT_ROUTE,
            aliases=aliases,
            agent_id=agent_id,
            parse_args=True,
            category="Agent",
        )
        for agent_id, description, aliases in _AGENT_ROUTES
    )


async def _load_skill_command_bindings() -> tuple[CommandDef, ...]:
    """Load skill command bindings from all agent profiles.

    Reads AgentProfile.command_bindings from the DB and converts each
    CommandBinding to a CommandDef(kind=SKILL) for registration in the
    CommandRegistry.

    Returns an empty tuple if no bindings exist or on any error.
    """
    from app.channels.routing.command_defs import (
        CommandDef,
        CommandKind,
    )

    try:
        from sqlalchemy import select

        from app.database.connection import get_session
        from app.database.models import Agent

        async with get_session() as session:
            result = await session.execute(select(Agent))
            agents = result.scalars().all()

        if not agents:
            return ()

        from app.database.repositories.agent_repo import AgentRepository

        commands: list[CommandDef] = []
        for agent in agents:
            profile = AgentRepository._agent_to_profile(agent)
            if not profile.command_bindings:
                continue
            for binding in profile.command_bindings:
                skill_label = ",".join(binding.skill_ids) if binding.skill_ids else "?"
                commands.append(
                    CommandDef(
                        name=binding.command_name,
                        description=binding.description or f"Invoke skill: {skill_label}",
                        kind=CommandKind.SKILL,
                        aliases=binding.aliases,
                        skill_ids=binding.skill_ids,
                        instruction=binding.instruction,
                        parse_args=True,
                        category="Skill",
                    )
                )

        return tuple(commands)
    except Exception:
        logger.warning("Failed to load skill command bindings", exc_info=True)
        return ()


async def reload_skill_command_bindings() -> None:
    """Reload skill command bindings from DB and update the live CommandRegistry.

    Called when agent command_bindings change (create/update/delete).
    """
    new_commands = await _load_skill_command_bindings()
    channel_gateway.update_skill_commands(new_commands)
    logger.info(
        "Reloaded skill command bindings: %d commands registered",
        len(new_commands),
    )
