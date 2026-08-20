"""Profile output suffix injection (personality + response locale).

[INPUT]
- app.database.dto::PersonalityStyleLiteral (POS: Agent personality style enum SSOT)
- app.ai_agents.personality_templates::get_personality_template (POS: Personality suffix templates)
- myrm_agent_harness.utils.response_locale::build_response_locale_suffix (POS: Agent output locale/formality suffix from engine_params)

[OUTPUT]
- apply_profile_output_suffixes(): append personality and response_locale suffixes
  to user_instructions tail (prompt-cache safe; not system_prompt prefix).

[POS]
Server SSOT for profile-driven output constraints. Used by Web, Channel, Cron,
Kanban, Eval, Voice (agent_bridge + realtime + gemini_live), Subagent, and
Goal stream continuation entry points.
"""

from __future__ import annotations

import logging
from typing import cast

from myrm_agent_harness.utils.response_locale import build_response_locale_suffix

from app.database.dto import PersonalityStyleLiteral

logger = logging.getLogger(__name__)


def apply_profile_output_suffixes(
    user_instructions: str | None,
    *,
    personality_style: str | None = None,
    engine_params: dict[str, object] | None = None,
    agent_id: str | None = None,
) -> str | None:
    """Append personality and response-locale suffixes to user_instructions tail."""
    instructions = user_instructions

    from app.ai_agents.personality_templates import (
        DEFAULT_PERSONALITY_STYLE,
        get_personality_template,
    )

    if personality_style and personality_style != DEFAULT_PERSONALITY_STYLE:
        try:
            template = get_personality_template(cast(PersonalityStyleLiteral, personality_style))
            personality_suffix = f"\n\n**Communication Style**: {template.system_prompt_suffix}"
            instructions = f"{instructions}{personality_suffix}" if instructions else personality_suffix.strip()
        except Exception:
            logger.warning(
                "Invalid personality style '%s' for agent '%s'",
                personality_style,
                agent_id,
            )

    locale_suffix = build_response_locale_suffix(engine_params)
    if locale_suffix:
        instructions = f"{instructions}{locale_suffix}" if instructions else locale_suffix.strip()

    return instructions
