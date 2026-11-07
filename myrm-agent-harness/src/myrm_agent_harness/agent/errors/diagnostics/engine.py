"""LLM error diagnostic engine.

[INPUT]
- diagnostics.account_diagnosis::diagnose_account (POS: Billing, provider-policy and API key diagnostics)
- diagnostics.catalog_result::build_catalog_result (POS: DiagnosticResult assembly from the locale catalogue)
- diagnostics.cooldown_hint::format_cooldown_hint (POS: Cooldown hint rendering for rate-limit diagnostics)
- diagnostics.i18n::get_locale_manager (POS: Framework-level i18n for LLM error diagnostics)
- diagnostics.provider_words::error_text, keyword_text, provider_message (POS: The provider's words an error is read by and shown with)
- diagnostics.recovery_actions::build_recovery_actions (POS: Recovery action catalogue of the diagnostics engine)
- diagnostics.transport_diagnosis::diagnose_transport, infer_service_name (POS: TLS and connection diagnostics)
- diagnostics.types::DiagnosticResult, ErrorContext (POS: Error diagnostic data structures)
- toolkits.llms.errors.classifier::ErrorKind, classify_error, classify_failover_reason (POS: LLM error classifier for failover decisions)
- toolkits.llms.errors.error_types::FailoverReason (POS: Three-layer error classification system)
- toolkits.llms.transport::LLMCallError (POS: the failures of a model call, carrying the HTTP status they stand for)

[OUTPUT]
- LLMErrorDiagnostic: Static classifier that maps LLM exceptions to localized DiagnosticResult

[POS]
LLM error diagnostic engine. Classifies exceptions from LLM calls into actionable categories
with localized user messages and resolution steps. Transport failures are diagnosed by their own module first. The
keyword families read the provider's own sentence, not the transport's framing or the numeric fields of its JSON
body: a status digit is data the shared classifier weighs, not a word of the provider. What the provider wrote can
still point elsewhere than its status does (a WAF page, a subscription-tier gate, a policy block), so the failures
the classifier outranks the text on are answered right after the transport family.
Account failures follow, then the model, rate-limit, response-format, context and timeout families, every
failure the shared classifier recognizes beyond them (a rejected key, billing, overload, safety filter, rejected
request), the unknown fallback and the truncation diagnoses.
"""

import re
from dataclasses import replace

from myrm_agent_harness.agent.errors.diagnostics.account_diagnosis import diagnose_account
from myrm_agent_harness.agent.errors.diagnostics.catalog_result import build_catalog_result
from myrm_agent_harness.agent.errors.diagnostics.cooldown_hint import format_cooldown_hint
from myrm_agent_harness.agent.errors.diagnostics.i18n import get_locale_manager
from myrm_agent_harness.agent.errors.diagnostics.provider_words import error_text, keyword_text, provider_message
from myrm_agent_harness.agent.errors.diagnostics.recovery_actions import build_recovery_actions
from myrm_agent_harness.agent.errors.diagnostics.transport_diagnosis import diagnose_transport, infer_service_name
from myrm_agent_harness.agent.errors.diagnostics.types import (
    DiagnosticResult,
    ErrorContext,
)
from myrm_agent_harness.toolkits.llms.errors.classifier import ErrorKind, classify_failover_reason, kind_of_reason
from myrm_agent_harness.toolkits.llms.errors.error_types import FailoverReason
from myrm_agent_harness.toolkits.llms.transport import LLMCallError

_MODEL_NOT_FOUND_KEYWORDS = ("model not found", "model does not exist", "unknown model")
_RATE_LIMIT_KEYWORDS = ("rate limit", "too many requests", "quota exceeded")

# Families that need nothing beyond their catalogue entry, in priority order.
_KEYWORD_FAMILIES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "response_format_error",
        ("must be in json format", "schema validation error", "invalid json format", "malformed json"),
    ),
    ("context_overflow", ("context length", "token limit", "context window", "too long", "max tokens")),
    ("timeout", ("timeout", "timed out", "time out")),
)

# Failures the shared classifier recognizes by the status code the SDK parsed as well as by the provider's wording,
# so the keyword families above miss some of them: each reads from its own catalogue entry instead of the raw
# exception text. A missing model is left out; it is read by the model family above, which knows whether the
# endpoint is a custom one.
_CLASSIFIED_KIND_TYPES: dict[ErrorKind, str] = {
    ErrorKind.AUTH: "api_key",
    ErrorKind.BILLING: "billing",
    ErrorKind.CONTEXT_OVERFLOW: "context_overflow",
    ErrorKind.TIMEOUT: "timeout",
    ErrorKind.RESPONSE_FORMAT_ERROR: "response_format_error",
    ErrorKind.OVERLOADED: "overloaded",
    ErrorKind.SAFETY_BLOCK: "safety_block",
    ErrorKind.CHALLENGE_BLOCKED: "challenge_blocked",
}

# A gateway that answers 504 gave up waiting for the model, whatever words its page uses. The shared classifier files
# the status under overload, which is what the failover policy needs; the user is told the cause.
_GATEWAY_TIMEOUT = 504

# Classifications shown in the provider's own words, because no card of ours names what the plan or account lacks.
_PROVIDER_WORDS_REASONS = frozenset({FailoverReason.LONG_CONTEXT_TIER, FailoverReason.PROVIDER_POLICY_BLOCKED})


def _diagnose_rejected_request(
    exc: Exception,
    context: ErrorContext | None,
    locale: str,
    cooldown_remaining_ms: int | None,
) -> DiagnosticResult:
    """A rejected request tells what the provider objected to.

    With no provider payload there is nothing to quote, so the card names the model the request was for, or states
    the failure plainly when the caller knows no model.
    """
    message = provider_message(exc)
    if message is not None:
        return build_catalog_result("format_error", locale, cooldown_remaining_ms, error_message=message)
    if context and context.model_name:
        return build_catalog_result(
            "format_error", locale, cooldown_remaining_ms, entry="format_error_model", model_name=context.model_name
        )
    return build_catalog_result("format_error", locale, cooldown_remaining_ms, entry="format_error_generic")


def _diagnose_outranking(
    exc: Exception, reason: FailoverReason, locale: str, cooldown_remaining_ms: int | None
) -> DiagnosticResult | None:
    """A failure whose classification outranks the keywords found in the exception text.

    The keyword families below read a WAF challenge page (403) as a rejected key, a subscription tier gate (429) as
    a rate limit and a provider policy block (403, 404) as a missing model. The classifier weighs the status against
    the provider's payload, so its verdict wins for these. A tier gate and a policy block are no failure of the key,
    the model or the window: the provider's own words say what the plan or the account lacks.
    """
    if reason is FailoverReason.CHALLENGE_BLOCKED:
        return build_catalog_result("challenge_blocked", locale, cooldown_remaining_ms)
    if reason in _PROVIDER_WORDS_REASONS:
        return build_catalog_result("unknown", locale, cooldown_remaining_ms, error_message=error_text(exc))
    return None


def _is_model_not_found(full_text: str) -> bool:
    return (
        any(kw in full_text for kw in _MODEL_NOT_FOUND_KEYWORDS)
        or re.search(r"(?<!\d)404(?!\d)", full_text) is not None
        or ("model" in full_text and "not found" in full_text)
    )


def _diagnose_model_not_found(
    full_text: str,
    context: ErrorContext | None,
    locale: str,
    cooldown_remaining_ms: int | None,
) -> DiagnosticResult:
    """A missing model on a local service (Ollama, LM Studio) reads differently from one on a hosted provider."""
    if context and context.model_name:
        model_name = context.model_name
    else:
        model_match = re.search(r"model[:\s]+([a-zA-Z0-9\-._/]+)", full_text)
        model_name = model_match.group(1) if model_match else "unknown"

    if context and context.is_custom_endpoint:
        return build_catalog_result(
            "custom_model_not_found",
            locale,
            cooldown_remaining_ms,
            model_name=model_name,
            service_name=infer_service_name(context.base_url),
        )
    return build_catalog_result("model", locale, cooldown_remaining_ms, model_name=model_name)


def _diagnose_rate_limit(locale: str, cooldown_remaining_ms: int | None) -> DiagnosticResult:
    result = build_catalog_result("rate_limit", locale, cooldown_remaining_ms)
    # A known wait is already in the message; a second, different one would contradict it.
    if format_cooldown_hint(cooldown_remaining_ms, locale):
        return result
    wait_step = get_locale_manager().translate_optional("rate_limit", "wait_step", locale)
    if not wait_step:
        return result
    return replace(result, resolution_steps=[wait_step, *result.resolution_steps])


class LLMErrorDiagnostic:
    """LLM错误智能诊断器

    Example:
        >>> # 基础诊断(无上下文)
        >>> try:
        ...     # LLM调用
        ...     pass
        ... except Exception as e:
        ...     result = LLMErrorDiagnostic.diagnose(e)
        ...     print(result.user_message)
        ...
        >>> # 精准诊断(带ErrorContext, 支持自定义端点)
        >>> from myrm_agent_harness.agent.errors.diagnostics import ErrorContext
        >>> try:
        ...     # Ollama调用
        ...     pass
        ... except Exception as e:
        ...     context = ErrorContext(
        ...         model_name="llama3.2",
        ...         is_custom_endpoint=True,
        ...         base_url="http://localhost:11434"
        ...     )
        ...     result = LLMErrorDiagnostic.diagnose(e, context)
        ...     print(result.user_message)  # "Unable to connect to Ollama (http://localhost:11434)"
    """

    @staticmethod
    def diagnose(
        exc: Exception,
        context: ErrorContext | None = None,
        locale: str | None = None,
        cooldown_remaining_ms: int | None = None,
    ) -> DiagnosticResult:
        """诊断LLM错误并返回清晰的解决方案

        Args:
            exc: LLM调用产生的异常
            context: 错误上下文(可选, 用于精准诊断)
            locale: 语言代码(可选, None=自动检测)
            cooldown_remaining_ms: 冷却剩余时间(毫秒, 可选)

        Returns:
            DiagnosticResult: 错误诊断结果
        """
        if locale is None:
            locale = get_locale_manager().detect_locale()

        full_text = keyword_text(exc)

        # 0-1. Transport (TLS, connection) family, then the failures the classifier outranks the text on
        transport = diagnose_transport(exc, full_text, context, locale, cooldown_remaining_ms)
        if transport is not None:
            return transport

        reason = classify_failover_reason(exc)
        outranking = _diagnose_outranking(exc, reason, locale, cooldown_remaining_ms)
        if outranking is not None:
            return outranking

        # 2-3. Account family (billing, provider policy, API key)
        account = diagnose_account(exc, full_text, locale, cooldown_remaining_ms)
        if account is not None:
            return account

        # 4. Model not found (精准自定义端点诊断)
        if _is_model_not_found(full_text):
            return _diagnose_model_not_found(full_text, context, locale, cooldown_remaining_ms)

        # 5. Rate limit
        if any(kw in full_text for kw in _RATE_LIMIT_KEYWORDS) or re.search(r"(?<!\d)429(?!\d)", full_text):
            return _diagnose_rate_limit(locale, cooldown_remaining_ms)

        # 6-8. Response format, context overflow, timeout
        for error_type, keywords in _KEYWORD_FAMILIES:
            if any(kw in full_text for kw in keywords):
                return build_catalog_result(error_type, locale, cooldown_remaining_ms)
        if isinstance(exc, LLMCallError) and exc.status_code == _GATEWAY_TIMEOUT:
            return build_catalog_result("timeout", locale, cooldown_remaining_ms)

        # 9. Failures only the shared classifier recognizes
        kind = kind_of_reason(reason)
        if kind is ErrorKind.FORMAT_ERROR:
            return _diagnose_rejected_request(exc, context, locale, cooldown_remaining_ms)
        if kind is ErrorKind.RATE_LIMIT:
            return _diagnose_rate_limit(locale, cooldown_remaining_ms)
        classified_type = _CLASSIFIED_KIND_TYPES.get(kind)
        if classified_type is not None:
            return build_catalog_result(classified_type, locale, cooldown_remaining_ms)

        # 10. Generic fallback
        return build_catalog_result("unknown", locale, cooldown_remaining_ms, error_message=error_text(exc))

    @staticmethod
    def diagnose_truncation(
        truncation_type: str,
        locale: str | None = None,
    ) -> DiagnosticResult:
        """Diagnose length truncation scenarios.

        Args:
            truncation_type: One of "thinking_budget_exhausted", "tool_call_truncated",
                "tool_call_retry", "text_continuation", "text_continuation_exhausted"
            locale: Language code (None = auto-detect)

        Returns:
            DiagnosticResult with localized user message and resolution steps.
        """
        if locale is None:
            locale = get_locale_manager().detect_locale()
        return build_catalog_result(truncation_type, locale)

    @staticmethod
    def get_recovery_actions(error_type: str, locale: str | None = "en") -> list[dict[str, str]]:
        """Return localized actionable recovery buttons for the given error type."""
        return build_recovery_actions(error_type, locale)
