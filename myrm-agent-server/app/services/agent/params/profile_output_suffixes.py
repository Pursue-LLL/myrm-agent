"""Profile output suffix injection (personality + response locale).

[INPUT]
- app.ai_agents.personality_templates::render_personality_block (POS: Personality style block renderer)
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

from myrm_agent_harness.utils.response_locale import build_response_locale_suffix

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

    if personality_style:
        from app.ai_agents.personality_templates import (
            DEFAULT_PERSONALITY_STYLE,
            render_personality_block,
        )

        try:
            style_block = render_personality_block(personality_style)
        except Exception as exc:  # 防御：风格渲染异常绝不能阻断 Agent 请求
            style_block = None
            logger.warning(
                "Failed to render personality style '%s' for agent '%s': %s",
                personality_style,
                agent_id,
                exc,
            )

        if style_block:
            instructions = f"{instructions}\n\n{style_block}" if instructions else style_block
        elif personality_style != DEFAULT_PERSONALITY_STYLE:
            logger.warning(
                "Unknown personality style '%s' for agent '%s'; no style block injected",
                personality_style,
                agent_id,
            )

    locale_suffix = build_response_locale_suffix(engine_params)
    if locale_suffix:
        instructions = f"{instructions}{locale_suffix}" if instructions else locale_suffix.strip()

    return instructions
