from __future__ import annotations

import logging
from dataclasses import replace
from typing import TYPE_CHECKING

from myrm_agent_harness.agent.extensions.protocols import AgentExtension

if TYPE_CHECKING:
    from langchain.agents.middleware import AgentMiddleware
    from langchain_core.tools import BaseTool
    from myrm_agent_harness.agent.base_agent import BaseAgent

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
        self.channel_name = channel_name
        self.security_config_raw = security_config_raw
        self.agent_security_raw = agent_security_raw
        self.declared_capabilities = declared_capabilities
        self.declared_allowed_roots = declared_allowed_roots

    @property
    def name(self) -> str:
        return "SecurityPolicyExtension"

    async def on_agent_init(self, agent: BaseAgent) -> None:
        from myrm_agent_harness.agent.security.channel_presets import (
            build_channel_security_config,
        )
        from myrm_agent_harness.agent.security.types import PIIAction, PrivacyPolicy

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

        agent.config = replace(
            agent.config,
            security_config=build_channel_security_config(
                self.channel_name,
                self.security_config_raw,
                agent_security_raw=self.agent_security_raw,
                declared_capabilities=self.declared_capabilities,
                declared_allowed_roots=self.declared_allowed_roots,
                local_mode=is_local_mode(),
                privacy_policy=privacy_policy,
            ),
        )

    async def on_agent_shutdown(self, agent: BaseAgent) -> None:
        pass

    def get_tools(self) -> list[BaseTool] | None:
        return None

    def get_middlewares(self) -> list[AgentMiddleware[object, object]] | None:
        return None
