"""
[METADATA]
Audits active Anthropic provider configuration for third-party subscription policy risks.

[POS]
Server infrastructure health diagnostics component.
"""
from __future__ import annotations

import logging
from app.core.infra.health.contracts import DiagnosticProtocol, HealthReport

logger = logging.getLogger(__name__)


class AnthropicSubscriptionPolicyDiagnostic(DiagnosticProtocol):
    """Audits active Anthropic provider configuration for third-party subscription policy risks."""

    async def check_health(self) -> HealthReport:
        try:
            from app.core.channel_bridge.config_loader import load_user_configs

            configs = await load_user_configs()
            model_name = (getattr(configs.model_cfg, "model", "") or "").lower()

            is_anthropic_model = "claude" in model_name or "anthropic" in model_name
            if not is_anthropic_model:
                return HealthReport(
                    component_name="AnthropicPolicyDoctor",
                    status="pass",
                    code="OK_ANTHROPIC_POLICY_INACTIVE",
                    message="Active model is not Anthropic Claude.",
                )

            api_key = getattr(configs.model_cfg, "api_key", None) or ""
            has_api_key = bool(api_key and not api_key.startswith("oauth_"))

            if has_api_key:
                return HealthReport(
                    component_name="AnthropicPolicyDoctor",
                    status="pass",
                    code="OK_ANTHROPIC_API_KEY_CONFIGURED",
                    message="Anthropic provider uses dedicated API Key (stable third-party route).",
                    detail=f"Model: {model_name}; dedicated API Key configured. Immune to web subscription policy blocks.",
                )

            return HealthReport(
                component_name="AnthropicPolicyDoctor",
                status="warn",
                code="WARN_ANTHROPIC_SUBSCRIPTION_POLICY",
                message="Anthropic Claude subscription is subject to third-party harness policy restrictions.",
                detail="Anthropic policy limits web subscriptions (Claude Pro/Max) to first-party clients. Third-party harnesses may experience intermittent policy blocks (403/429) or long-context gates.",
                fix_suggestion="Configure an Anthropic API Key in Settings -> Models, or configure a fallback model (e.g. OpenAI GPT-4o / DeepSeek).",
                meta_data={"model": model_name, "has_api_key": False},
            )
        except Exception as exc:
            logger.warning("Anthropic policy diagnostic failed: %s", exc)
            return HealthReport(
                component_name="AnthropicPolicyDoctor",
                status="pass",
                code="OK_ANTHROPIC_POLICY_SKIPPED",
                message="Anthropic policy diagnostic skipped or uninitialized.",
            )
