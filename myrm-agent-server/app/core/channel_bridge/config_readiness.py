"""Provider configuration readiness checker.

Implements ConfigReadinessChecker from framework layer to check if user has
at least one enabled and valid LLM provider configured.

[INPUT]
- providers_dict: dict from UserConfig table (providers config)

[OUTPUT]
- ConfigReadinessResult: provider configuration status

[POS]
Business-layer provider readiness check. Inherits framework-level
ConfigReadinessChecker interface, implements provider-specific validation logic.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from myrm_agent_harness.agent.config import ConfigReadinessResult

from app.core.channel_bridge.model_resolver import _extract_all_active_keys

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class ProviderConfigChecker:
    """Check if user has configured at least one enabled LLM provider."""

    def check(self, config: dict[str, object] | None = None) -> ConfigReadinessResult:
        """Check provider configuration readiness.

        Args:
            config: providers_dict from UserConfig table

        Returns:
            ConfigReadinessResult with provider status
        """
        if not config:
            return ConfigReadinessResult(
                is_ready=False,
                missing_items=["providers"],
                suggestions=[
                    "Configure at least one LLM provider (OpenAI, Anthropic, Ollama, etc.)",
                    "Go to Settings > Model Service to add providers",
                ],
            )

        providers: list[dict[str, object]] = config.get("providers", [])  # type: ignore[assignment]
        if not providers:
            return ConfigReadinessResult(
                is_ready=False,
                missing_items=["providers"],
                suggestions=[
                    "Add at least one LLM provider in Settings",
                    "Supported providers: OpenAI, Anthropic, Google, DeepSeek, Ollama, etc.",
                ],
            )

        enabled_providers = [p for p in providers if p.get("isEnabled")]
        if not enabled_providers:
            return ConfigReadinessResult(
                is_ready=False,
                missing_items=["enabled_provider"],
                suggestions=[
                    "Enable at least one provider in Settings > Model Service",
                    f"You have {len(providers)} provider(s) configured but all are disabled",
                ],
            )

        valid_providers = []
        for p in enabled_providers:
            provider_id = str(p.get("id", ""))
            keys = _extract_all_active_keys(p)
            if not keys:
                logger.warning("Provider %s enabled but has no usable auth/no-auth policy", provider_id)
                continue

            valid_providers.append(provider_id)

        if not valid_providers:
            return ConfigReadinessResult(
                is_ready=False,
                missing_items=["valid_api_key"],
                suggestions=[
                    "Add valid API keys to your enabled providers",
                    "For local providers (Ollama, LM Studio), ensure the service is running",
                ],
            )

        logger.debug("Provider config check passed: %d valid provider(s) found", len(valid_providers))
        return ConfigReadinessResult(
            is_ready=True,
            extra_info={"valid_providers": valid_providers},
        )


class SearchConfigChecker:
    """Check if user has configured and enabled a search service."""

    def check(self, search_services_dict: dict[str, object] | None = None) -> ConfigReadinessResult:
        from app.core.channel_bridge.config_parsers import is_search_user_configured

        if not is_search_user_configured(search_services_dict):
            return ConfigReadinessResult(
                is_ready=False,
                missing_items=["search_service"],
                suggestions=[
                    "Enable SearXNG from the chat setup banner (requires local Docker profile)",
                    "Go to Settings > Search Service to add Tavily or other providers",
                ],
            )

        return ConfigReadinessResult(is_ready=True)


__all__ = ["ProviderConfigChecker", "SearchConfigChecker"]
