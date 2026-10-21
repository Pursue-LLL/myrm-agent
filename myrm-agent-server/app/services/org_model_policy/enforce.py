"""Org model policy enforcement at agent build time.

[INPUT]
- app.services.config.service::ConfigService (POS: 用户配置 CRUD)
- app.config.deploy_mode::is_sandbox (POS: 沙箱部署模式判定)
- app.services.agent.moa_preset_resolver (POS: MoA overlay 引用模型解析)

[OUTPUT]
- enforce_org_model_policy: fail-closed model whitelist check on GeneralAgent wrapper
- OrgModelPolicyViolation: user-facing violation exception

[POS]
Server 业务层 org model policy 执行 SSOT。在 agent build 后校验 primary/fallback/MoA
引用模型是否符合 CP sync 落盘的白名单；sandbox Config 读失败 fail-closed。
"""

from __future__ import annotations

import logging
from fnmatch import fnmatch
from typing import TYPE_CHECKING

from app.services.org_model_policy.normalize import normalize_org_model_policy_pattern

if TYPE_CHECKING:
    from app.ai_agents.general_agent.agent import GeneralAgent

logger = logging.getLogger(__name__)


class OrgModelPolicyViolation(Exception):
    """Raised when a configured model is not allowed by organization policy."""

    def __init__(
        self,
        model_name: str,
        allowed_patterns: list[str],
        *,
        reason: str | None = None,
    ) -> None:
        self.model_name = model_name
        self.allowed_patterns = allowed_patterns
        if reason is not None:
            super().__init__(reason)
            return
        super().__init__(
            f"The model '{model_name}' is restricted by your organization's policy. "
            "Please select an approved model or contact your administrator."
        )


def _collect_moa_reference_model_names(
    engine_params: dict[str, object] | None,
) -> set[str]:
    """Collect MoA overlay reference model names from agent engine_params."""
    from app.services.agent.moa_preset_resolver import (
        iter_all_reference_selections,
        moa_overlay_from_engine_params,
    )

    overlay = moa_overlay_from_engine_params(engine_params)
    if overlay is None:
        return set()
    names: set[str] = set()
    for item in iter_all_reference_selections(overlay):
        model = item.get("model")
        if isinstance(model, str) and model:
            names.add(model)
    return names


async def enforce_org_model_policy(agent_wrapper: GeneralAgent) -> None:
    """Fail-closed check: reject models not whitelisted by org policy.

    No-op when no policy is configured (local/Tauri or no org restriction).
    Raises OrgModelPolicyViolation on mismatch to give instant user feedback.
    """
    from app.services.config.service import ConfigService

    try:
        config_svc = ConfigService()
        record = await config_svc.get("orgModelPolicy")
    except Exception as exc:
        logger.exception("Org model policy read failed")
        from app.config.deploy_mode import is_sandbox

        if not is_sandbox():
            return
        raise OrgModelPolicyViolation(
            "",
            [],
            reason=("Organization model policy could not be verified. Please try again later or contact your administrator."),
        ) from exc

    if record is None:
        return
    patterns: list[str] = record.value.get("allowed_patterns", []) if isinstance(record.value, dict) else []
    if not patterns:
        return

    model_names: set[str] = set()
    for cfg in (
        agent_wrapper.model_cfg,
        agent_wrapper.lite_model_cfg,
        agent_wrapper.fallback_model_cfg,
        agent_wrapper.safety_fallback_model_cfg,
        agent_wrapper.reasoning_model_cfg,
    ):
        name = getattr(cfg, "model", None) if cfg is not None else None
        if name:
            model_names.add(name)

    model_names.update(
        _collect_moa_reference_model_names(
            getattr(agent_wrapper, "engine_params", None),
        )
    )

    for model_name in model_names:
        if not any(fnmatch(model_name, normalize_org_model_policy_pattern(p)) for p in patterns):
            logger.warning(
                "Org model policy violation: model '%s' not in allowed patterns %s",
                model_name,
                patterns,
            )
            raise OrgModelPolicyViolation(model_name, patterns)
