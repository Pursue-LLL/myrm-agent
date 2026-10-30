"""Billing, provider-policy and API key diagnostics of the LLM error engine.

[INPUT]
- diagnostics.cooldown_hint::format_cooldown_hint (POS: Cooldown hint rendering for rate-limit diagnostics)
- diagnostics.i18n::get_locale_manager (POS: Framework-level i18n for LLM error diagnostics)
- diagnostics.types::DiagnosticResult (POS: Error diagnostic data structures)
- toolkits.llms.adapters.wire.normalizer::ResponsesStreamError (POS: Responses wire stream errors)

[OUTPUT]
- diagnose_account: maps a billing, provider-policy or API key failure to a localized DiagnosticResult, None for any other error

[POS]
Account half of the diagnostic engine: errors where the provider answered but refused the caller (no
balance, a provider policy, a rejected key). The engine calls it right after the transport family.
"""

import re

from myrm_agent_harness.agent.errors.diagnostics.cooldown_hint import format_cooldown_hint
from myrm_agent_harness.agent.errors.diagnostics.i18n import get_locale_manager
from myrm_agent_harness.agent.errors.diagnostics.types import DiagnosticResult


def diagnose_account(
    exc: Exception,
    full_text: str,
    locale: str,
    cooldown_remaining_ms: int | None,
) -> DiagnosticResult | None:
    """Diagnose billing, provider-policy and API key failures in priority order; None when none applies."""
    locale_manager = get_locale_manager()

    # 2. Billing / insufficient balance errors
    billing_keywords = [
        "billing",
        "insufficient balance",
        "insufficient funds",
        "insufficient credits",
        "insufficient quota",
        "payment required",
        "exceeded your current quota",
        "exceeded quota",
        "credit balance",
        "account is deactivated",
        "top up your credits",
        "run out of credits",
        "used all available credits",
        "grok subscription",
        "余额不足",
        "额度不足",
        "欠费",
        "请充值",
    ]
    if any(kw in full_text for kw in billing_keywords) or re.search(r"(?<!\d)402(?!\d)", full_text):
        user_message = locale_manager.translate("billing", "user_message", locale)
        resolution_steps = locale_manager.translate("billing", "resolution_steps", locale)

        cooldown_hint = format_cooldown_hint(cooldown_remaining_ms, locale)
        user_message += cooldown_hint

        return DiagnosticResult(
            error_type="billing",
            user_message=user_message,
            resolution_steps=resolution_steps,
            is_retryable=False,
            locale=locale,
        )

    # 2b. OpenCode Go contributor training policy (muse-spark contributor)
    from myrm_agent_harness.toolkits.llms.adapters.wire.normalizer import ResponsesStreamError

    if isinstance(exc, ResponsesStreamError):
        user_message = locale_manager.translate("opencode_training_policy", "user_message", locale)
        resolution_steps = locale_manager.translate("opencode_training_policy", "resolution_steps", locale)
        return DiagnosticResult(
            error_type="opencode_training_policy",
            user_message=user_message,
            resolution_steps=resolution_steps,
            is_retryable=False,
            locale=locale,
        )

    training_policy_keywords = [
        "trainingnotallowed",
        "datapolicyerror",
        "allowtraining",
    ]
    compact = full_text.replace(" ", "").replace("_", "")
    if any(kw in compact for kw in training_policy_keywords) or (
        "muse-spark" in full_text
        and "contributor" in full_text
        and "training" in full_text
        and "not allowed" in full_text
    ):
        user_message = locale_manager.translate("opencode_training_policy", "user_message", locale)
        resolution_steps = locale_manager.translate("opencode_training_policy", "resolution_steps", locale)
        return DiagnosticResult(
            error_type="opencode_training_policy",
            user_message=user_message,
            resolution_steps=resolution_steps,
            is_retryable=False,
            locale=locale,
        )

    # 3. API key errors
    api_key_keywords = [
        "invalid api key",
        "authentication failed",
        "unauthorized",
    ]
    if any(kw in full_text for kw in api_key_keywords) or re.search(r"(?<!\d)(401|403)(?!\d)", full_text):
        user_message = locale_manager.translate("api_key", "user_message", locale)
        resolution_steps = locale_manager.translate("api_key", "resolution_steps", locale)

        cooldown_hint = format_cooldown_hint(cooldown_remaining_ms, locale)
        user_message += cooldown_hint

        return DiagnosticResult(
            error_type="api_key",
            user_message=user_message,
            resolution_steps=resolution_steps,
            is_retryable=False,
            locale=locale,
        )

    return None
