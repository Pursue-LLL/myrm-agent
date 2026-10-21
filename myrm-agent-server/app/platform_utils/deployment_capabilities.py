"""Deployment capability registry — semantic flags derived once at startup.

[INPUT]
- app.config.deploy_mode::DeployMode, get_deploy_mode, is_local_mode, is_webui_remote_mode (POS: 部署模式与运行方式枚举与判断)

[OUTPUT]
- DeploymentCapabilities: 部署能力语义标志数据类
- get_deployment_capabilities: 单例缓存获取当前进程部署能力标志

[POS]
部署能力语义注册表。启动时一次性计算并缓存当前部署环境支持的语义能力位。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

from app.config.deploy_mode import DeployMode, get_deploy_mode, is_local_mode, is_webui_remote_mode


@dataclass(frozen=True, slots=True)
class DeploymentCapabilities:
    """What this server instance is allowed to do in the current deploy mode."""

    allows_local_skills: bool
    requires_api_key_auth: bool
    uses_platform_budget: bool
    validates_mcp_response_size: bool
    uses_config_encryption: bool
    requires_strict_ws_auth: bool
    uses_cp_entitlements: bool
    trust_cp_proxy_identity: bool
    enables_auth_audit: bool
    default_metrics_enabled: bool
    runs_sandbox_startup_validation: bool
    skips_webui_model_preflight: bool
    is_sandbox_instance: bool


@lru_cache(maxsize=1)
def get_deployment_capabilities() -> DeploymentCapabilities:
    """Build cached capability snapshot for the current process."""
    mode = get_deploy_mode()
    sandbox = mode == DeployMode.SANDBOX
    local = is_local_mode()
    remote = is_webui_remote_mode()

    env_allow_local = os.getenv("MYRM_ALLOW_LOCAL_SKILLS")
    if env_allow_local is not None:
        allows_local = env_allow_local.strip().lower() in {"1", "true", "yes", "on"}
    else:
        allows_local = local or sandbox

    return DeploymentCapabilities(
        allows_local_skills=allows_local,
        requires_api_key_auth=sandbox or remote,
        uses_platform_budget=sandbox,
        validates_mcp_response_size=sandbox,
        uses_config_encryption=sandbox,
        requires_strict_ws_auth=sandbox,
        uses_cp_entitlements=sandbox,
        trust_cp_proxy_identity=sandbox,
        enables_auth_audit=sandbox or remote,
        default_metrics_enabled=not (local or sandbox),
        runs_sandbox_startup_validation=sandbox,
        skips_webui_model_preflight=sandbox or not local,
        is_sandbox_instance=sandbox,
    )


def _reset_capabilities_cache_for_testing() -> None:
    get_deployment_capabilities.cache_clear()


__all__ = [
    "DeploymentCapabilities",
    "get_deployment_capabilities",
    "_reset_capabilities_cache_for_testing",
]
