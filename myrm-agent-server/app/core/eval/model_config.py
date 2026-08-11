"""Model-config resolution shared across eval reports and judge injection.

[INPUT]
- myrm_agent_harness.eval::JudgeConfig
- myrm_agent_harness.api.config::ConfigIncompleteError
- app.core.channel_bridge.config_loader::load_user_configs
- app.services.agent.profile.profile_resolver::get_agent_profile_resolver (POS: 统一智能体配置解析服务，带 TTL 缓存)

[OUTPUT]
- _resolve_agent_model_label: label of the evaluated agent's model.
- _resolve_judge_config: LLM-as-a-Judge credentials plus display label.

[POS]
统一解析评测所涉及的模型配置：被评测 agent 模型标签（profile 声明优先、兜底
用户 model_cfg）供 manifest 与 Memory A/B 报告披露，judge 模型配置（复用用户
LLM 凭证）供语义断言与 judge 前置检查注入。
"""

from __future__ import annotations

from myrm_agent_harness.api.config import ConfigIncompleteError
from myrm_agent_harness.eval import JudgeConfig


async def _resolve_agent_model_label(profile_id: str | None) -> str:
    """Resolve the model label of the evaluated agent.

    Prefers the agent profile's declared model, falling back to the user's
    active model config (``model_cfg``) when no profile is selected or the
    profile does not declare a model. Returns ``"unknown"`` when neither
    source is available. ``_build_eval_manifest`` and the Memory A/B report
    use the same resolution so benchmark reports and Memory A/B reports
    disclose the identical label.
    """
    from app.core.channel_bridge.config_loader import load_user_configs

    if profile_id:
        from app.services.agent.profile.profile_resolver import (
            get_agent_profile_resolver,
        )

        resolved = await get_agent_profile_resolver().resolve(profile_id)
        if resolved and resolved.model:
            return resolved.model

    configs = await load_user_configs()
    model_cfg = getattr(configs, "model_cfg", None)
    model = getattr(model_cfg, "model", None)
    return str(model) if model else "unknown"


async def _resolve_judge_config() -> tuple[JudgeConfig | None, str]:
    """Resolve the LLM judge configuration from the user's active model.

    The judge for semantic assertions (LLM-as-a-Judge) runs independently of
    the evaluated agent, so it can reuse the user's own LLM credentials even
    in ``benchmark_mode`` (which only strips the *agent's* user-specific
    configuration). Returns the judge credentials plus a display label for the
    manifest (e.g. ``"deepseek/deepseek-chat"`` or ``"none"``).
    """
    from app.core.channel_bridge.config_loader import load_user_configs

    try:
        configs = await load_user_configs()
    except ConfigIncompleteError:
        # No LLM provider configured — the judge cannot run. The router turns
        # this into explicit guidance before the benchmark starts.
        return None, "none"
    model_cfg = getattr(configs, "model_cfg", None)
    if model_cfg is None or not getattr(model_cfg, "model", None):
        return None, "none"
    model = str(model_cfg.model)
    judge = JudgeConfig(
        model=model,
        api_key=getattr(model_cfg, "api_key", None),
        api_base=getattr(model_cfg, "base_url", None),
    )
    return judge, model
