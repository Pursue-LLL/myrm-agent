"""Channel preamble user-instruction enrichment.

[INPUT]
app.channels.types::InboundMessage, ResolvedAgentProfile (POS: 渠道入站与 Agent 配置)
app.ai_agents.personality_templates::render_personality_block (POS: 会话级沟通风格块渲染)

[OUTPUT]
enrich_channel_user_instructions(): 合并团队协议、渠道能力约束、IM 行为策略 Persona、
会话级沟通风格（`/personality`）与 response_locale_policy 后缀后的 instructions。

[POS]
preamble 子模块：将渠道/Agent 输出约束注入 user_instructions 尾部。
"""

from __future__ import annotations

from app.channels.types import InboundMessage
from app.services.agent.profile.profile_resolver import ResolvedAgentProfile


async def enrich_channel_user_instructions(
    msg: InboundMessage,
    *,
    user_instructions: str | None,
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
            warnings.append("- DO NOT use Markdown formatting (like bold, italics, links, or code blocks). Use plain text only.")

        if warnings:
            warning_str = (
                "IMPORTANT: You are communicating via a channel with the following limitations:\n"
                + "\n".join(warnings)
                + "\nDescribe things using text instead."
            )
            instructions = f"{instructions}\n\n{warning_str}" if instructions else warning_str

        if not caps.edit and not caps.markdown:
            im_persona = (
                "You are communicating via a mobile IM app with a small screen.\n"
                "- Keep replies short and conversational, like chatting.\n"
                "- When you need to output more than ~200 characters of content, "
                "write it to a workspace file using file tools, then reply with only "
                "a one-sentence summary and the file path.\n"
                "- When the user's intent is unclear, ask at most 1-2 key questions before acting."
            )
            instructions = f"{instructions}\n\n{im_persona}" if instructions else im_persona

    from app.ai_agents.personality_templates import render_personality_block
    from app.services.agent.params.response_locale_suffix import apply_response_locale_suffix

    session_style = msg.metadata.get("personality_style")
    style_block = render_personality_block(session_style if isinstance(session_style, str) else None)
    if style_block:
        instructions = f"{instructions}\n\n{style_block}" if instructions else style_block

    instructions = apply_response_locale_suffix(
        instructions,
        engine_params=resolved_profile.engine_params if resolved_profile else None,
    )

    return instructions or ""
