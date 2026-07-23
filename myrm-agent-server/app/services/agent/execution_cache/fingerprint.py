"""Execution fingerprint — server inputs for harness runtime spec hashing.

[INPUT]
- app.ai_agents.general_agent.agent::GeneralAgent (POS: 业务 Agent 包装层)

[OUTPUT]
- compute_execution_fingerprint, build_execution_scope_key

[POS]
execution_cache 指纹层。将 MCP/skill/harness 输入稳定哈希为 scope key。
"""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.ai_agents.general_agent.agent import GeneralAgent


def _stable_json(value: object) -> object:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): _stable_json(v) for k, v in sorted(value.items(), key=lambda item: item[0])}
    if isinstance(value, (list, tuple)):
        return [_stable_json(v) for v in value]
    if hasattr(value, "model_dump"):
        dumped = value.model_dump(mode="json")
        return _stable_json(dumped)
    return str(value)


def _serialize_mcp_configs(agent_wrapper: GeneralAgent) -> list[dict[str, object]]:
    configs: list[dict[str, object]] = []
    for cfg in agent_wrapper.mcp_config or []:
        if hasattr(cfg, "model_dump"):
            dumped = cfg.model_dump(mode="json")
            if isinstance(dumped, dict):
                configs.append({str(k): _stable_json(v) for k, v in sorted(dumped.items())})
    configs.sort(key=lambda item: str(item.get("name", "")))
    return configs


def compute_execution_fingerprint(agent_wrapper: GeneralAgent) -> str:
    """Hash wrapper-level inputs that affect ``build_general_agent`` output."""
    from app.core.skills.config_version import get_skill_config_version
    from app.server.stack_epoch import read_stack_epoch

    stack_epoch = read_stack_epoch()
    harness_fp = stack_epoch["harness_fingerprint"] if stack_epoch else ""

    payload: dict[str, object] = {
        "agent_id": agent_wrapper.agent_id or "default",
        "model": agent_wrapper.model_cfg.model,
        "provider": getattr(agent_wrapper.model_cfg, "provider", None),
        "fallback_model": (
            agent_wrapper.fallback_model_cfg.model if agent_wrapper.fallback_model_cfg else None
        ),
        "lite_model": agent_wrapper.lite_model_cfg.model if agent_wrapper.lite_model_cfg else None,
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
        "enable_file_ops": agent_wrapper.enable_file_ops,
        "enable_shell_tools": agent_wrapper.enable_shell_tools,
        "enable_memory": agent_wrapper.enable_memory,
        "incognito_mode": agent_wrapper.incognito_mode,
        "enable_wiki": agent_wrapper.enable_wiki,
        "enable_kanban": agent_wrapper.enable_kanban,
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
    }

    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]


def build_execution_scope_key(chat_id: str | None, agent_id: str | None) -> str | None:
    if not chat_id or not chat_id.strip():
        return None
    return f"{chat_id.strip()}:{agent_id or 'default'}"
