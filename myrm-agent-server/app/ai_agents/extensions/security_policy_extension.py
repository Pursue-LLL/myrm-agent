from __future__ import annotations

import logging
from dataclasses import replace
from typing import TYPE_CHECKING

from myrm_agent_harness.agent.extensions.protocols import AgentExtension

if TYPE_CHECKING:
    from langchain.agents.middleware import AgentMiddleware
    from langchain_core.tools import BaseTool
    from myrm_agent_harness.agent.base_agent import BaseAgent
    from myrm_agent_harness.agent.security.types import SecurityConfig

    from app.ai_agents.general_agent.agent import GeneralAgent

logger = logging.getLogger(__name__)


class SecurityPolicyExtension(AgentExtension):
    """Extension that configures the agent's security policies and PII handling."""

    def __init__(
        self,
        privacy_enabled: bool,
        privacy_s2_action: str,
        privacy_s3_action: str,
        channel_name: str,
        security_config_raw: dict[str, object],
        agent_security_raw: dict[str, object],
        declared_capabilities: list[str],
        declared_allowed_roots: list[str],
        privacy_custom_keywords_s2: list[str] | None = None,
        privacy_custom_keywords_s3: list[str] | None = None,
        privacy_custom_patterns_s2: list[str] | None = None,
        privacy_custom_patterns_s3: list[str] | None = None,
        privacy_sensitive_tools_s2: list[str] | None = None,
        privacy_sensitive_tools_s3: list[str] | None = None,
        privacy_deep_scan: bool = False,
        plan_confirm_enabled: bool = False,
    ) -> None:
        self.privacy_enabled = privacy_enabled
        self.privacy_s2_action = privacy_s2_action
        self.privacy_s3_action = privacy_s3_action
        self.privacy_deep_scan = privacy_deep_scan
        self.privacy_custom_keywords_s2 = tuple(privacy_custom_keywords_s2 or ())
        self.privacy_custom_keywords_s3 = tuple(privacy_custom_keywords_s3 or ())
        self.privacy_custom_patterns_s2 = tuple(privacy_custom_patterns_s2 or ())
        self.privacy_custom_patterns_s3 = tuple(privacy_custom_patterns_s3 or ())
        self.privacy_sensitive_tools_s2 = tuple(privacy_sensitive_tools_s2 or ())
        self.privacy_sensitive_tools_s3 = tuple(privacy_sensitive_tools_s3 or ())
        self.plan_confirm_enabled = plan_confirm_enabled
        self.channel_name = channel_name
        self.security_config_raw = security_config_raw
        self.agent_security_raw = agent_security_raw
        self.declared_capabilities = declared_capabilities
        self.declared_allowed_roots = declared_allowed_roots

    @property
    def name(self) -> str:
        return "SecurityPolicyExtension"

    def _build_security_config(self) -> "SecurityConfig":
        from myrm_agent_harness.agent.security.channel_presets import (
            build_channel_security_config,
        )
        from myrm_agent_harness.agent.security.types import PIIAction, PrivacyPolicy, SecurityConfig

        from app.config.deploy_mode import is_local_mode

        privacy_policy = (
            PrivacyPolicy(
                enabled=self.privacy_enabled,
                s2_action=PIIAction(self.privacy_s2_action),
                s3_action=PIIAction(self.privacy_s3_action),
                custom_keywords_s2=self.privacy_custom_keywords_s2,
                custom_keywords_s3=self.privacy_custom_keywords_s3,
                custom_patterns_s2=self.privacy_custom_patterns_s2,
                custom_patterns_s3=self.privacy_custom_patterns_s3,
                sensitive_tools_s2=self.privacy_sensitive_tools_s2,
                sensitive_tools_s3=self.privacy_sensitive_tools_s3,
                deep_scan=self.privacy_deep_scan,
            )
            if self.privacy_enabled
            else None
        )

        security_config = build_channel_security_config(
            self.channel_name,
            self.security_config_raw,
            agent_security_raw=self.agent_security_raw,
            declared_capabilities=self.declared_capabilities,
            declared_allowed_roots=self.declared_allowed_roots,
            local_mode=is_local_mode(),
            privacy_policy=privacy_policy,
        )

        if self.plan_confirm_enabled and not security_config.plan_confirm_enabled:
            object.__setattr__(security_config, "plan_confirm_enabled", True)

        return security_config

    def apply_security_config(self, agent: BaseAgent) -> None:
        from dataclasses import is_dataclass

        built = self._build_security_config()
        cfg = agent.config
        if not is_dataclass(cfg) or isinstance(cfg, type):
            logger.warning(
                "apply_security_config skipped: unsupported config type=%s",
                type(cfg).__name__,
            )
            return
        agent.config = replace(cfg, security_config=built)
        logger.info(
            "apply_security_config agent=%s yolo=%s auto_mode=%s",
            getattr(cfg, "agent_id", ""),
            built.yolo_mode_enabled,
            built.auto_mode_enabled,
        )

    async def on_agent_init(self, agent: BaseAgent) -> None:
        self.apply_security_config(agent)

    async def on_agent_shutdown(self, agent: BaseAgent) -> None:
        pass

    def get_tools(self) -> list[BaseTool] | None:
        return None

    def get_middlewares(self) -> list[AgentMiddleware[object, object]] | None:
        return None


async def sync_wrapper_security_from_store(agent_wrapper: "GeneralAgent") -> None:
    """Reload persisted securityConfig onto the wrapper before each stream turn."""
    from app.core.channel_bridge.config_cache import invalidate_user_configs_cache
    from app.core.channel_bridge.config_loader import load_user_configs

    invalidate_user_configs_cache()
    configs = await load_user_configs()
    if configs and configs.security_config_dict is not None:
        agent_wrapper.security_config_raw = dict(configs.security_config_dict)


def refresh_wrapper_security_config(agent_wrapper: "GeneralAgent") -> None:
    """Re-apply merged security policy on a POOLED SkillAgent before each stream turn."""
    skill_agent = agent_wrapper.agent
    if skill_agent is None:
        return
    SecurityPolicyExtension(
        privacy_enabled=agent_wrapper.privacy_enabled,
        privacy_s2_action=agent_wrapper.privacy_s2_action,
        privacy_s3_action=agent_wrapper.privacy_s3_action,
        privacy_custom_keywords_s2=agent_wrapper.privacy_custom_keywords_s2,
        privacy_custom_keywords_s3=agent_wrapper.privacy_custom_keywords_s3,
        privacy_custom_patterns_s2=agent_wrapper.privacy_custom_patterns_s2,
        privacy_custom_patterns_s3=agent_wrapper.privacy_custom_patterns_s3,
        privacy_sensitive_tools_s2=agent_wrapper.privacy_sensitive_tools_s2,
        privacy_sensitive_tools_s3=agent_wrapper.privacy_sensitive_tools_s3,
        privacy_deep_scan=agent_wrapper.privacy_deep_scan,
        plan_confirm_enabled=agent_wrapper.enable_plan_confirm,
        channel_name=agent_wrapper.channel_name,
        security_config_raw=agent_wrapper.security_config_raw or {},
        agent_security_raw=agent_wrapper.agent_security_raw or {},
        declared_capabilities=list(agent_wrapper.declared_capabilities),
        declared_allowed_roots=list(agent_wrapper.declared_allowed_roots),
    ).apply_security_config(skill_agent)
