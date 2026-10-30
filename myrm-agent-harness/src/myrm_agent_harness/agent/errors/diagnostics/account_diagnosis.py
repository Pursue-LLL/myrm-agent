"""Billing, provider-policy and API key diagnostics of the LLM error engine.

[INPUT]
- diagnostics.catalog_result::build_catalog_result (POS: DiagnosticResult assembly from the locale catalogue)
- diagnostics.types::DiagnosticResult (POS: Error diagnostic data structures)
- toolkits.llms.adapters.wire.normalizer::ResponsesStreamError (POS: Responses wire stream errors)

[OUTPUT]
- diagnose_account: maps a billing, provider-policy or API key failure to a localized DiagnosticResult, None for any other error

[POS]
Account half of the diagnostic engine: errors where the provider answered but refused the caller (no
balance, a provider policy, a rejected key). The engine calls it right after the transport family.
"""

import re

from myrm_agent_harness.agent.errors.diagnostics.catalog_result import build_catalog_result
from myrm_agent_harness.agent.errors.diagnostics.types import DiagnosticResult

_BILLING_KEYWORDS = (
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
)
_TRAINING_POLICY_KEYWORDS = (
    "trainingnotallowed",
    "datapolicyerror",
    "allowtraining",
)
_API_KEY_KEYWORDS = (
    "invalid api key",
    "authentication failed",
    "unauthorized",
)


def _is_training_policy_block(full_text: str) -> bool:
    """OpenCode Go rejecting a muse-spark contributor model whose workspace did not opt in to training."""
    compact = full_text.replace(" ", "").replace("_", "")
    return any(kw in compact for kw in _TRAINING_POLICY_KEYWORDS) or (
        "muse-spark" in full_text
        and "contributor" in full_text
        and "training" in full_text
        and "not allowed" in full_text
    )


def diagnose_account(
    exc: Exception,
    full_text: str,
    locale: str,
    cooldown_remaining_ms: int | None,
) -> DiagnosticResult | None:
    """Diagnose billing, provider-policy and API key failures in priority order; None when none applies."""
    # 2. Billing / insufficient balance errors
    if any(kw in full_text for kw in _BILLING_KEYWORDS) or re.search(r"(?<!\d)402(?!\d)", full_text):
        return build_catalog_result("billing", locale, cooldown_remaining_ms)

    # 2b. OpenCode Go contributor training policy (muse-spark contributor)
    from myrm_agent_harness.toolkits.llms.adapters.wire.normalizer import ResponsesStreamError

    if isinstance(exc, ResponsesStreamError) or _is_training_policy_block(full_text):
        return build_catalog_result("opencode_training_policy", locale)

    # 3. API key errors
    if any(kw in full_text for kw in _API_KEY_KEYWORDS) or re.search(r"(?<!\d)(401|403)(?!\d)", full_text):
        return build_catalog_result("api_key", locale, cooldown_remaining_ms)

    return None
