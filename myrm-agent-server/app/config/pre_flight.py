"""配置启动前验证

在应用启动前验证配置，快速失败（Fail Fast），减少试错时间。

[INPUT]
- settings: 应用配置（Settings）
- app.services.agent.platform_config::webui_model_preflight_warning (POS: WebUI 平台级模型配置)
- harness.agent.config.validator.check_config_health: 框架层配置健康检查

[OUTPUT]
- PreflightResult: 验证结果（errors, warnings, infos）

[POS]
配置验证层。启动前进行配置验证；local/tauri 对未配置 WebUI 默认模型输出 warning，error 仍阻塞启动。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from myrm_agent_harness.agent.config import check_config_health
from myrm_agent_harness.api import AgentConfig

from .settings import settings


@dataclass(frozen=True, slots=True)
class PreflightResult:
    """配置预检结果"""

    errors: list[str]
    """阻塞性错误（必须修复才能启动）"""

    warnings: list[str]
    """警告信息（建议修复）"""

    infos: list[str]
    """信息提示"""

    def has_errors(self) -> bool:
        """是否有阻塞性错误"""
        return len(self.errors) > 0

    def print_report(self) -> None:
        """输出验证报告"""
        print("[CONFIG] Pre-flight check starting...")

        if self.infos:
            for info in self.infos:
                print(f"[CONFIG] ℹ️  {info}")

        if self.warnings:
            for warning in self.warnings:
                print(f"[CONFIG] ⚠️  Warning: {warning}")

        if self.errors:
            for error in self.errors:
                print(f"[CONFIG] ✗ Error: {error}")
            print("\nFailed to start due to config errors. Fix them and retry.\n")
        else:
            print("[CONFIG] ✓ Pre-flight check passed")


def preflight_check_config() -> PreflightResult:
    """启动前配置验证

    1. 验证必需环境变量
    2. 调用框架层 check_config_health()
    3. 验证路径存在性
    4. local/tauri：WebUI 默认模型 warning（skip pytest/sandbox）
    5. 生成结构化报告

    Returns:
        PreflightResult: 验证结果
    """
    errors: list[str] = []
    warnings: list[str] = []
    infos: list[str] = []

    # 1. Check deploy mode
    from app.config.deploy_mode import DeployMode, get_deploy_mode

    deploy_mode = get_deploy_mode()
    infos.append(f"Deploy mode: {deploy_mode.value}")

    # 2. Check database paths
    if deploy_mode in (DeployMode.LOCAL, DeployMode.TAURI):
        sqlite_path = Path(settings.database.sqlite_path).expanduser()
        if not sqlite_path.parent.exists():
            try:
                sqlite_path.parent.mkdir(parents=True, exist_ok=True)
                infos.append(f"Created database directory: {sqlite_path.parent}")
            except Exception as e:
                errors.append(f"Failed to create database directory: {e}")

    # 3. Call harness-layer config health check (if AgentConfig available)
    try:
        from myrm_agent_harness.api import LLMConfig

        # Create minimal AgentConfig for validation
        agent_config = AgentConfig(
            llm=LLMConfig(model="dummy", api_key="dummy"),
            use_prompt_caching=settings.cache.prompt_caching,
            recursion_limit=100,  # Default value for validation
        )
        issues = check_config_health(agent_config)

        for issue in issues:
            if issue.level == "error":
                msg = issue.message
                if issue.suggestion:
                    msg += f" (Suggestion: {issue.suggestion})"
                errors.append(msg)
            elif issue.level == "warning":
                msg = issue.message
                if issue.suggestion:
                    msg += f" (Suggestion: {issue.suggestion})"
                warnings.append(msg)
            elif issue.level == "info":
                infos.append(issue.message)
    except Exception as e:
        warnings.append(f"Failed to run harness config health check: {e}")

    # 4. WebUI default model (local/tauri only; warning, non-blocking)
    from app.services.agent.platform_config import webui_model_preflight_warning

    webui_warning = webui_model_preflight_warning()
    if webui_warning:
        warnings.append(webui_warning)

    # 5. Pydantic validation passed (settings already validated by Pydantic at import time)
    infos.append("Pydantic validation passed")

    return PreflightResult(errors=errors, warnings=warnings, infos=infos)
