"""AgentProfile → AgentResponse serialization helpers.

[INPUT]
myrm_agent_harness.backends.profiles.types::AgentProfile (POS: Agent 配置模型)
database.dto::AgentResponse, ModelSelection, ... (POS: API 响应契约)

[OUTPUT]
_to_agent_response, _metadata_as_mapping, _build_model_selection 等工具函数

[POS]
Agent 序列化共享层。被 agent.py / agent_portability.py / templates.py 引用。
"""

from __future__ import annotations

from datetime import datetime
from typing import TypeGuard, get_args

from myrm_agent_harness.backends.profiles.types import AgentProfile

from app.ai_agents.personality_templates import DEFAULT_PERSONALITY_STYLE
from app.core.memory.adapters.policy import memory_policy_to_dict
from app.database.dto import (
    AgentMemoryPolicyConfig,
    AgentResponse,
    AgentSessionPolicyConfig,
    CommandBindingConfig,
    ModelSelection,
    PersonalityStyleLiteral,
    WorkspacePolicyLiteral,
)
from app.services.agent.agent_service import HIDDEN_SYSTEM_PROMPT


def _is_valid_personality(value: object) -> TypeGuard[PersonalityStyleLiteral]:
    return isinstance(value, str) and value in get_args(PersonalityStyleLiteral)


def _safe_personality(raw: object) -> PersonalityStyleLiteral:
    """Sanitize personality_style from DB, falling back to default for invalid values."""
    if _is_valid_personality(raw):
        return raw
    if _is_valid_personality(DEFAULT_PERSONALITY_STYLE):
        return DEFAULT_PERSONALITY_STYLE
    return "professional"


def _metadata_as_mapping(agent: AgentProfile) -> dict[str, object]:
    raw = agent.metadata
    if not raw:
        return {}
    return {str(k): v for k, v in raw.items()}


def _meta_str(meta: dict[str, object], key: str) -> str | None:
    v = meta.get(key)
    return v if isinstance(v, str) else None


def _meta_str_list(meta: dict[str, object], key: str, *, default: list[str] | None = None) -> list[str]:
    v = meta.get(key)
    if isinstance(v, list):
        return [str(x) for x in v]
    return list(default or [])


def _meta_str_list_or_none(meta: dict[str, object], key: str) -> list[str] | None:
    v = meta.get(key)
    if v is None:
        return None
    if isinstance(v, list):
        return [str(x) for x in v]
    return None


def _meta_dict_or_none(meta: dict[str, object], key: str) -> dict[str, object] | None:
    v = meta.get(key)
    if isinstance(v, dict):
        return {str(k2): val for k2, val in v.items()}
    return None


def _meta_list_or_empty(meta: dict[str, object], key: str) -> list[dict[str, object]]:
    v = meta.get(key)
    if isinstance(v, list):
        return [item for item in v if isinstance(item, dict)]
    return []


def _meta_list_or_none(meta: dict[str, object], key: str) -> list[dict[str, str]] | None:
    v = meta.get(key)
    if isinstance(v, list) and v:
        return [item for item in v if isinstance(item, dict)]
    return None


_WORKSPACE_POLICY_MAP: dict[str, WorkspacePolicyLiteral] = {
    "ISOLATED_COPY": "ISOLATED_COPY",
    "READ_ONLY_SANDBOX": "READ_ONLY_SANDBOX",
}


def _workspace_policy_from_metadata(raw: object) -> WorkspacePolicyLiteral:
    return _WORKSPACE_POLICY_MAP.get(str(raw), "INHERIT_REQUESTER") if raw else "INHERIT_REQUESTER"


def _response_memory_policy(agent: AgentProfile) -> AgentMemoryPolicyConfig | None:
    raw = memory_policy_to_dict(agent.memory_policy)
    if raw is None:
        return None
    return AgentMemoryPolicyConfig.model_validate(raw)


def _response_session_policy(
    metadata: dict[str, object],
) -> AgentSessionPolicyConfig | None:
    raw = metadata.get("session_policy")
    if not isinstance(raw, dict):
        return None
    return AgentSessionPolicyConfig.model_validate(raw)


def _build_model_selection(model: str | None, metadata: dict[str, object]) -> ModelSelection | None:
    """Build ModelSelection from stored model_selection JSON or fallback to basic."""
    full = metadata.get("model_selection_full")
    if isinstance(full, dict) and full.get("model"):
        return ModelSelection(
            providerId=full.get("providerId", "auto"),
            model=full["model"],
            fallbackProviderId=full.get("fallbackProviderId"),
            fallbackModel=full.get("fallbackModel"),
            safetyFallbackProviderId=full.get("safetyFallbackProviderId"),
            safetyFallbackModel=full.get("safetyFallbackModel"),
            modelKwargs=full.get("modelKwargs"),
            routingEnabled=full.get("routingEnabled"),
            lightProviderId=full.get("lightProviderId"),
            lightModel=full.get("lightModel"),
            reasoningProviderId=full.get("reasoningProviderId"),
            reasoningModel=full.get("reasoningModel"),
        )
    if model:
        return ModelSelection(providerId="auto", model=model)
    return None


def _resolve_enabled_builtin_tools(agent: AgentProfile) -> list[str] | None:
    """Resolve enabled builtin tool IDs from AgentProfile (tools_allowed or metadata)."""
    if agent.tools_allowed is not None:
        return list(agent.tools_allowed)
    return _meta_str_list_or_none(_metadata_as_mapping(agent), "enabled_builtin_tools")


def _to_agent_response(
    agent: AgentProfile,
    show_system_prompt: bool = False,
    snapshot_count: int = 0,
    snapshot_saved: bool | None = None,
) -> AgentResponse:
    """Convert AgentProfile to API response DTO."""
    metadata = _metadata_as_mapping(agent)
    system_prompt = agent.system_prompt
    enabled_tools = _resolve_enabled_builtin_tools(agent)

    return AgentResponse(
        id=agent.id,
        user_id="local",
        name=agent.display_name or agent.id,
        description=agent.description,
        avatar_url=agent.avatar,
        home_directory=_meta_str(metadata, "home_directory"),
        is_built_in=agent.built_in,
        agent_type=metadata.get("agent_type", "individual") or "individual",
        system_prompt=system_prompt if show_system_prompt else HIDDEN_SYSTEM_PROMPT,
        mcp_ids=_meta_str_list(metadata, "mcp_ids", default=[]),
        mcp_tool_selections=_meta_dict_or_none(metadata, "mcp_tool_selections"),
        skill_ids=agent.skills or [],
        skill_configs=agent.skill_configs,
        enabled_builtin_tools=enabled_tools,
        browser_source=_meta_str(metadata, "browser_source"),
        dialog_policy=_meta_str(metadata, "dialog_policy"),
        session_recording=_meta_str(metadata, "session_recording"),
        auto_restore_domains=_meta_str_list(metadata, "auto_restore_domains", default=[]),
        suggestion_prompts=_meta_str_list_or_none(metadata, "suggestion_prompts"),
        model_selection=_build_model_selection(agent.model, metadata),
        security_overrides=_meta_dict_or_none(metadata, "security_overrides"),
        default_security_preset=_meta_str(metadata, "default_security_preset"),
        prompt_mode=metadata.get("prompt_mode", "full") or "full",
        personality_style=_safe_personality(metadata.get("personality_style")),
        subagent_ids=_meta_str_list(metadata, "subagent_ids", default=[]),
        max_iterations=agent.max_iterations,
        workspace_policy=_workspace_policy_from_metadata(metadata.get("workspace_policy", "INHERIT_REQUESTER")),
        memory_policy=_response_memory_policy(agent),
        session_policy=_response_session_policy(metadata),
        engine_params=_meta_dict_or_none(metadata, "engine_params"),
        openapi_services=_meta_list_or_empty(metadata, "openapi_services"),
        command_bindings=(
            [
                CommandBindingConfig(
                    command_name=b.command_name,
                    skill_ids=list(b.skill_ids),
                    description=b.description,
                    aliases=list(b.aliases),
                    instruction=b.instruction,
                )
                for b in agent.command_bindings
            ]
            if agent.command_bindings
            else None
        ),
        notify_targets=_meta_list_or_none(metadata, "notify_targets"),
        busy_input_mode=(
            _meta_str(metadata, "busy_input_mode")
            if _meta_str(metadata, "busy_input_mode") in ("redirect", "steer", "queue")
            else None
        ),
        cron_post_run_verify=bool(metadata.get("cron_post_run_verify", False)),
        allow_discovery=bool(metadata.get("allow_discovery", True)),
        created_at=agent.created_at or datetime.now(),
        updated_at=agent.updated_at or datetime.now(),
        snapshot_count=snapshot_count,
        snapshot_saved=snapshot_saved,
    )
