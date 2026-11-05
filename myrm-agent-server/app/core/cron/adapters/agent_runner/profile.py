"""把绑定 Agent 的配置解析成 Cron 执行上下文。

[POS]
agent_runner 的 profile 引导层；只读 Agent Profile，不创建任务、不写库。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from myrm_agent_harness.toolkits.cron.types import CronJob

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.memory.config import AgentMemoryPolicy

    from app.services.agent.profile.profile_resolver import ResolvedAgentProfile


@dataclass(slots=True)
class CronAgentProfileBootstrap:
    user_instructions: str | None = None
    skill_ids: list[str] = field(default_factory=list)
    subagent_ids: list[str] | None = None
    security_raw: dict[str, object] | None = None
    max_iterations: int | None = None
    memory_policy: "AgentMemoryPolicy | None" = None
    engine_params: dict[str, object] | None = None
    model_override: str | None = None
    enabled_builtin_tools: list[str] = field(default_factory=list)
    auto_restore_domains: list[str] = field(default_factory=list)
    memory_decay_profile: str | None = None
    memory_extraction_preset: str | None = None
    cron_post_run_verify: bool = False
    trusted_desktop_apps: tuple[dict[str, str], ...] = ()
    resolved: "ResolvedAgentProfile | None" = None


async def resolve_cron_agent_profile(job: CronJob) -> CronAgentProfileBootstrap:
    agent_skill_ids: list[str] = []
    agent_subagent_ids: list[str] | None = None
    agent_security_raw: dict[str, object] | None = None
    agent_max_iterations: int | None = None
    agent_memory_policy = None
    agent_engine_params = None
    user_instructions: str | None = None
    agent_model_override: str | None = None
    from app.services.agent.profile.profile_resolver import (
        DEFAULT_ENABLED_BUILTIN_TOOLS,
    )

    enabled_builtin_tools: list[str] = list(DEFAULT_ENABLED_BUILTIN_TOOLS)
    auto_restore_domains: list[str] = []
    memory_decay_profile: str | None = None
    memory_extraction_preset: str | None = None
    cron_post_run_verify = False
    trusted_desktop_apps: tuple[dict[str, str], ...] = ()
    resolved = None

    if job.agent_id:
        from app.services.agent.profile.profile_resolver import (
            get_agent_profile_resolver,
        )

        resolved = await get_agent_profile_resolver().resolve(job.agent_id)
        if resolved:
            if resolved.system_prompt:
                user_instructions = resolved.system_prompt
            agent_skill_ids = list(resolved.skill_ids)
            agent_subagent_ids = list(resolved.subagent_ids) if resolved.subagent_ids else None
            agent_security_raw = resolved.security_overrides
            agent_max_iterations = resolved.max_iterations
            agent_memory_policy = resolved.memory_policy
            agent_engine_params = resolved.engine_params
            agent_model_override = resolved.model
            enabled_builtin_tools = list(resolved.enabled_builtin_tools)
            auto_restore_domains = list(resolved.auto_restore_domains)
            raw_decay = resolved.memory_decay_profile
            memory_decay_profile = raw_decay if isinstance(raw_decay, str) else None
            raw_preset = resolved.memory_extraction_preset
            memory_extraction_preset = raw_preset if isinstance(raw_preset, str) else None
            cron_post_run_verify = resolved.cron_post_run_verify
            trusted_desktop_apps = resolved.trusted_desktop_apps

            if resolved.agent_type == "team":
                from app.ai_agents.team_protocol import (
                    build_leader_protocol_prompt,
                )

                leader_protocol = await build_leader_protocol_prompt(
                    agent_subagent_ids or [],
                    leader_id=job.agent_id,
                    dynamic_discovery=True,
                )
                user_instructions = f"{user_instructions}\n\n{leader_protocol}" if user_instructions else leader_protocol

            from app.services.agent.params.profile_output_suffixes import (
                apply_profile_output_suffixes,
            )

            user_instructions = apply_profile_output_suffixes(
                user_instructions,
                personality_style=resolved.personality_style,
                engine_params=resolved.engine_params,
                agent_id=job.agent_id,
            )

    return CronAgentProfileBootstrap(
        user_instructions=user_instructions,
        skill_ids=agent_skill_ids,
        subagent_ids=agent_subagent_ids,
        security_raw=agent_security_raw,
        max_iterations=agent_max_iterations,
        memory_policy=agent_memory_policy,
        engine_params=agent_engine_params,
        model_override=agent_model_override,
        enabled_builtin_tools=enabled_builtin_tools,
        auto_restore_domains=auto_restore_domains,
        memory_decay_profile=memory_decay_profile,
        memory_extraction_preset=memory_extraction_preset,
        cron_post_run_verify=cron_post_run_verify,
        trusted_desktop_apps=trusted_desktop_apps,
        resolved=resolved,
    )
