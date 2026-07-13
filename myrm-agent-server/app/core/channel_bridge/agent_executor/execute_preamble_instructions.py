"""Channel preamble user-instruction enrichment.

[INPUT]
app.channels.types::InboundMessage, ResolvedAgentProfile (POS: 渠道入站与 Agent 配置)

[OUTPUT]
enrich_channel_user_instructions(): 合并团队协议、渠道能力约束、人格模板后的 instructions。

[POS]
execute_preamble 子模块：将渠道/Agent/人格约束注入 user_instructions。
"""

from __future__ import annotations

import logging

from app.channels.types import InboundMessage
from app.services.agent.profile_resolver import ResolvedAgentProfile

logger = logging.getLogger(__name__)


async def enrich_channel_user_instructions(
    msg: InboundMessage,
    *,
    user_instructions: str,
    resolved_profile: ResolvedAgentProfile | None,
    agent_subagent_ids: list[str] | None,
    resolved_agent_id: str | None,
) -> str:
    instructions = user_instructions

    if resolved_profile and resolved_profile.agent_type == "team":
        from app.ai_agents.team_protocol import build_leader_protocol_prompt

        leader_protocol = await build_leader_protocol_prompt(
            agent_subagent_ids or [],
            leader_id=resolved_agent_id,
            dynamic_discovery=True,
        )
        instructions = f"{instructions}\n\n{leader_protocol}" if instructions else leader_protocol

    if hasattr(msg, "channel_capabilities") and msg.channel_capabilities:
        caps = msg.channel_capabilities
        warnings = []
        if not caps.media:
            warnings.append("- DO NOT attempt to generate or send any images, video, or audio.")
        if not caps.file_upload:
            warnings.append("- DO NOT attempt to generate or send any files or documents (like CSV, PDF, etc.).")
        if not caps.markdown:
            warnings.append(
                "- DO NOT use Markdown formatting (like bold, italics, links, or code blocks). Use plain text only."
            )

        if warnings:
            warning_str = (
                "IMPORTANT: You are communicating via a channel with the following limitations:\n"
                + "\n".join(warnings)
                + "\nDescribe things using text instead."
            )
            instructions = f"{instructions}\n\n{warning_str}" if instructions else warning_str

    from app.ai_agents.personality_templates import (
        DEFAULT_PERSONALITY_STYLE,
        PERSONALITY_TEMPLATES,
        get_personality_template,
    )

    raw_ps = (
        msg.metadata.get("personality_style")
        or (resolved_profile.personality_style if resolved_profile else None)
        or DEFAULT_PERSONALITY_STYLE
    )
    personality_style_key = str(raw_ps)
    if personality_style_key != DEFAULT_PERSONALITY_STYLE and personality_style_key in PERSONALITY_TEMPLATES:
        try:
            template = get_personality_template(personality_style_key)
            personality_suffix = f"\n\n**Communication Style**: {template.system_prompt_suffix}"
            instructions = (
                f"{instructions}{personality_suffix}" if instructions else personality_suffix.strip()
            )
        except Exception as e:
            logger.warning(
                "Failed to load personality template '%s': %s",
                personality_style_key,
                e,
            )

    return instructions
