"""Execution fingerprint — server inputs for harness runtime spec hashing.

[INPUT]
- app.ai_agents.general_agent.agent::GeneralAgent (POS: 通用 Agent 核心实现)

[OUTPUT]
- compute_execution_fingerprint, build_execution_scope_key

[POS]
execution_cache 指纹层。将影响 build_general_agent 输出的模型/技能/MCP/安全/记忆/工具/
隐私路由配置稳定哈希为 scope key；模型类字段统一经 _model_sig 提取 build 固化签名
（排除 api_key 等凭据池字段与 temperature 等调用级参数）。排除每 run 状态
（kanban_current_task_id、quote、force_skill_manage）与全局静态配置
（event_log_backend、tail_budget_ratio）——前者会使缓存永不命中，后者不构成差异源。
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from typing import TYPE_CHECKING

from pydantic import BaseModel

if TYPE_CHECKING:
    from app.ai_agents.general_agent.agent import GeneralAgent
    from app.core.types.business import ModelConfig


def _stable_json(value: object) -> object:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {
            str(k): _stable_json(v)
            for k, v in sorted(value.items(), key=lambda item: item[0])
        }
    if isinstance(value, (list, tuple)):
        return [_stable_json(v) for v in value]
    if isinstance(value, BaseModel):
        dumped = value.model_dump(mode="json")
        return _stable_json(dumped)
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return _stable_json(dataclasses.asdict(value))
    return str(value)


def _model_sig(model_cfg: ModelConfig | None) -> dict[str, object] | None:
    """Stable build signature for a model config.

    Only parameters solidified into ``build_general_agent`` output are kept:
    LLM wiring (base_url), harness spec model definition (custom_model_def,
    max_context_tokens) and capability gates (supports_vision/video).
    Credential-pool fields (api_key/api_keys/credential_pool_strategy) are
    excluded — key rotation does not change build semantics and keys must not
    enter the hash — along with call-time knobs (temperature/streaming/
    model_kwargs) that are not build inputs.
    """
    if model_cfg is None:
        return None
    return {
        "model": model_cfg.model,
        "provider": getattr(model_cfg, "provider", None),
        "base_url": model_cfg.base_url,
        "max_context_tokens": model_cfg.max_context_tokens,
        "supports_vision": model_cfg.supports_vision,
        "supports_video": model_cfg.supports_video,
        "custom_model_def": _stable_json(model_cfg.custom_model_def),
    }


def _model_list_sig(model_cfgs: list[ModelConfig] | None) -> list[dict[str, object] | None] | None:
    if not model_cfgs:
        return None
    return [_model_sig(cfg) for cfg in model_cfgs]


def _serialize_mcp_configs(agent_wrapper: GeneralAgent) -> list[dict[str, object]]:
    configs: list[dict[str, object]] = []
    for cfg in agent_wrapper.mcp_config or []:
        if isinstance(cfg, BaseModel):
            dumped = cfg.model_dump(mode="json")
            if isinstance(dumped, dict):
                configs.append(
                    {str(k): _stable_json(v) for k, v in sorted(dumped.items())}
                )
    configs.sort(key=lambda item: str(item.get("name", "")))
    return configs


def compute_execution_fingerprint(agent_wrapper: GeneralAgent) -> str:
    """Hash wrapper-level inputs that affect ``build_general_agent`` output."""
    from app.core.skills.config_version import get_skill_config_version
    from app.server.stack_epoch import read_stack_epoch
    from app.services.org_model_policy.revision import get_org_model_policy_revision

    stack_epoch = read_stack_epoch()
    harness_fp = stack_epoch["harness_fingerprint"] if stack_epoch else ""

    payload: dict[str, object] = {
        "agent_id": agent_wrapper.agent_id or "default",
        "model_cfg": _model_sig(agent_wrapper.model_cfg),
        "fallback_model_cfg": _model_sig(agent_wrapper.fallback_model_cfg),
        "lite_model_cfg": _model_sig(agent_wrapper.lite_model_cfg),
        "safety_fallback_model_cfg": _model_sig(
            agent_wrapper.safety_fallback_model_cfg
        ),
        "fallback_lite_model_cfg": _model_sig(agent_wrapper.fallback_lite_model_cfg),
        "light_model_cfg": _model_sig(agent_wrapper.light_model_cfg),
        "reasoning_model_cfg": _model_sig(agent_wrapper.reasoning_model_cfg),
        "vision_fallback_model_cfg": _model_sig(
            agent_wrapper.vision_fallback_model_cfg
        ),
        "vision_fallback_model_cfgs": _model_list_sig(
            agent_wrapper.vision_fallback_model_cfgs
        ),
        "video_fallback_model_cfgs": _model_list_sig(
            agent_wrapper.video_fallback_model_cfgs
        ),
        "prompt_mode": agent_wrapper.prompt_mode,
        "engine_params": _stable_json(agent_wrapper.engine_params),
        "skill_config_version": get_skill_config_version(),
        "harness_fingerprint": harness_fp,
        "skill_ids": sorted(agent_wrapper.skill_ids or []),
        "skill_configs": _stable_json(agent_wrapper.skill_configs),
        "subagent_ids": sorted(agent_wrapper.subagent_ids or []),
        "mcp_servers": _serialize_mcp_configs(agent_wrapper),
        "openapi_services": _stable_json(agent_wrapper.openapi_services),
        "external_agents": _stable_json(agent_wrapper.external_agents_config),
        "user_instructions": agent_wrapper.user_instructions or "",
        "max_iterations": agent_wrapper.max_iterations,
        "locale": agent_wrapper.locale,
        "channel_name": agent_wrapper.channel_name,
        "enable_web_search": agent_wrapper.enable_web_search,
        "enable_browser": agent_wrapper.enable_browser,
        "browser_source": getattr(agent_wrapper, "browser_source", None),
        "dialog_policy": getattr(agent_wrapper, "dialog_policy", None),
        "session_recording": getattr(agent_wrapper, "session_recording", None),
        "enable_computer_use": agent_wrapper.enable_computer_use,
        "file_access_mode": agent_wrapper.file_access_mode.value,
        "enable_shell_tools": agent_wrapper.enable_shell_tools,
        "enable_memory": agent_wrapper.enable_memory,
        "enable_memory_auto_extraction": agent_wrapper.enable_memory_auto_extraction,
        "memory_extraction_preset": agent_wrapper.memory_extraction_preset,
        "memory_decay_profile": agent_wrapper.memory_decay_profile,
        "embedding_config": _stable_json(agent_wrapper.embedding_config),
        "incognito_mode": agent_wrapper.incognito_mode,
        "enable_wiki": agent_wrapper.enable_wiki,
        "enable_kanban": agent_wrapper.enable_kanban,
        "kanban_tool_mode": agent_wrapper.kanban_tool_mode,
        "enable_cron_eager": agent_wrapper.enable_cron_eager,
        "enable_answer_tool": agent_wrapper.enable_answer_tool,
        "enable_planning": agent_wrapper.enable_planning,
        "enable_external_cli": agent_wrapper.enable_external_cli,
        "enable_render_ui": agent_wrapper.enable_render_ui,
        "enable_structured_clarify": agent_wrapper.enable_structured_clarify,
        "unattended_mode": agent_wrapper.unattended_mode,
        "declared_capabilities": list(agent_wrapper.declared_capabilities),
        "declared_allowed_roots": list(agent_wrapper.declared_allowed_roots),
        # Security policy must bust POOLED cache when YOLO/HITL or permissions change.
        "security_config_raw": _stable_json(agent_wrapper.security_config_raw),
        "agent_security_raw": _stable_json(agent_wrapper.agent_security_raw),
        "code_execution_allow_network": agent_wrapper.code_execution_allow_network,
        "notify_targets": _stable_json(agent_wrapper.notify_targets),
        "providers_dict": _stable_json(agent_wrapper.providers_dict),
        "privacy_routing_raw": _stable_json(agent_wrapper.privacy_routing_raw),
        "jit_subagents": _stable_json(agent_wrapper.jit_subagents),
        "force_delegate_agent": agent_wrapper.force_delegate_agent,
        # Org model policy revision busts POOLED cache after CP sandbox sync.
        "org_model_policy_revision": get_org_model_policy_revision(),
    }

    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]


def build_execution_scope_key(chat_id: str | None, agent_id: str | None) -> str | None:
    if not chat_id or not chat_id.strip():
        return None
    return f"{chat_id.strip()}:{agent_id or 'default'}"
