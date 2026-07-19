"""Built-in Agents Auto-Initialization

[INPUT]
app.database.models::Agent (POS: Agent 配置域模型)
app.database.connection::get_session (POS: DB 会话工厂)
app.services.agent.builtin_agent_specs::_BUILTIN_AGENTS (POS: 预置智能体规格定义)

[OUTPUT]
initialize_builtin_agents: 服务启动时自动创建预置智能体

[POS]
业务层预置智能体初始化。在服务启动时幂等创建 26 个内置智能体
（5 核心 + 2 搜索 + 5 扩展 + 14 垂直领域），
确保用户首次使用时有可用的默认智能体覆盖常见场景。
搜索智能体的提示词由 prompt_mode="search" 单一提供（KV Cache 稳定），
其 system_prompt 留空以避免在 Agent 模式下经 user_instructions 重复注入。
"""

import logging

from sqlalchemy import select

from app.database.connection import get_session
from app.database.models import Agent
from app.services.agent.builtin_agent_specs import (
    _BUILTIN_AGENTS,
    _TOOL_CODING,
    _TOOL_DEFAULT,
    _TOOL_DESIGN,
    _TOOL_MINIMAL,
    _TOOL_RESEARCH,
    _TOOL_VIDEO_STUDIO,
    _BuiltInAgentSpec,
)

__all__ = [
    "_BUILTIN_AGENTS",
    "_BuiltInAgentSpec",
    "_TOOL_CODING",
    "_TOOL_DEFAULT",
    "_TOOL_DESIGN",
    "_TOOL_MINIMAL",
    "_TOOL_RESEARCH",
    "_TOOL_VIDEO_STUDIO",
    "initialize_builtin_agents",
]

logger = logging.getLogger(__name__)


def _peripheral_skill_configs(skill_ids: tuple[str, ...]) -> dict[str, dict[str, object]]:
    """Default prebuilt skill bindings: peripheral (on-demand) to protect prompt cache."""
    return {skill_id: {"is_core": False} for skill_id in skill_ids}


async def initialize_builtin_agents() -> None:
    """Create or update built-in agents at startup.

    Idempotent: creates missing agents and updates spec-controlled fields
    (name, description, avatar, personality, system_prompt, suggestion_prompts)
    for existing ones to keep them in sync with code definitions.
    User-customizable fields (skill_ids, mcp_servers, etc.) are never overwritten.
    suggestion_prompts are only populated when the DB value is empty (protects user edits).

    Called once at server startup (lifespan Phase 1b).
    """
    async with get_session() as db:
        existing_result = await db.execute(select(Agent).where(Agent.id.in_([spec.id for spec in _BUILTIN_AGENTS])))
        existing_map: dict[str, Agent] = {a.id: a for a in existing_result.scalars().all()}

        created_count = 0
        updated_count = 0

        for spec in _BUILTIN_AGENTS:
            expected_avatar = f"icon:{spec.icon_id}"
            resolved_prompt = spec.system_prompt

            default_skills = list(spec.default_skill_ids)
            default_skill_configs = _peripheral_skill_configs(spec.default_skill_ids)

            if spec.id not in existing_map:
                agent_kwargs: dict[str, object] = {
                    "id": spec.id,
                    "name": spec.name,
                    "description": spec.description,
                    "avatar": expected_avatar,
                    "is_built_in": True,
                    "is_public": True,
                    "personality_style": spec.personality_style,
                    "system_prompt": resolved_prompt,
                    "skill_ids": default_skills,
                    "skill_configs": default_skill_configs or None,
                    "mcp_servers": [],
                    "subagent_ids": [],
                    "model_config": {},
                }
                if spec.enabled_builtin_tools is not None:
                    agent_kwargs["enabled_builtin_tools"] = list(spec.enabled_builtin_tools)
                if spec.prompt_mode != "full":
                    agent_kwargs["prompt_mode"] = spec.prompt_mode
                if spec.engine_params is not None:
                    agent_kwargs["engine_params"] = spec.engine_params
                if spec.memory_policy is not None:
                    agent_kwargs["memory_policy"] = spec.memory_policy
                if spec.suggestion_prompts:
                    agent_kwargs["suggestion_prompts"] = list(spec.suggestion_prompts)

                db.add(Agent(**agent_kwargs))
                created_count += 1
            else:
                agent = existing_map[spec.id]
                changed = _sync_existing_agent(agent, spec, expected_avatar, resolved_prompt,
                                               default_skills, default_skill_configs)
                if changed:
                    updated_count += 1

        if created_count > 0 or updated_count > 0:
            await db.commit()
            logger.info(
                "[Startup] Built-in agents: %d created, %d updated",
                created_count,
                updated_count,
            )
        else:
            logger.debug("[Startup] All built-in agents up to date")


def _sync_existing_agent(
    agent: Agent,
    spec: _BuiltInAgentSpec,
    expected_avatar: str,
    resolved_prompt: str,
    default_skills: list[str],
    default_skill_configs: dict[str, dict[str, object]] | None,
) -> bool:
    """Sync spec-controlled fields to an existing DB agent. Returns True if any field changed."""
    changed = False
    if not agent.skill_ids and default_skills:
        agent.skill_ids = default_skills
        agent.skill_configs = default_skill_configs or None
        changed = True
    if agent.name != spec.name:
        agent.name = spec.name
        changed = True
    if agent.description != spec.description:
        agent.description = spec.description
        changed = True
    if agent.avatar != expected_avatar:
        agent.avatar = expected_avatar
        changed = True
    if agent.personality_style != spec.personality_style:
        agent.personality_style = spec.personality_style
        changed = True
    if agent.system_prompt != resolved_prompt:
        agent.system_prompt = resolved_prompt
        changed = True
    if spec.enabled_builtin_tools is not None:
        expected_tools = list(spec.enabled_builtin_tools)
        if agent.enabled_builtin_tools != expected_tools:
            agent.enabled_builtin_tools = expected_tools
            changed = True
    if spec.prompt_mode != "full" and agent.prompt_mode != spec.prompt_mode:
        agent.prompt_mode = spec.prompt_mode
        changed = True
    if spec.engine_params is not None and agent.engine_params != spec.engine_params:
        agent.engine_params = spec.engine_params
        changed = True
    if spec.memory_policy is not None and agent.memory_policy != spec.memory_policy:
        agent.memory_policy = spec.memory_policy
        changed = True
    if spec.suggestion_prompts and not agent.suggestion_prompts:
        agent.suggestion_prompts = list(spec.suggestion_prompts)
        changed = True
    return changed
