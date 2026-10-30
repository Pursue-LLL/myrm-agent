"""LLM error diagnostic engine.

[INPUT]
- diagnostics.account_diagnosis::diagnose_account (POS: Billing, provider-policy and API key diagnostics)
- diagnostics.catalog_result::build_catalog_result (POS: DiagnosticResult assembly from the locale catalogue)
- diagnostics.cooldown_hint::format_cooldown_hint (POS: Cooldown hint rendering for rate-limit diagnostics)
- diagnostics.i18n::get_locale_manager (POS: Framework-level i18n for LLM error diagnostics)
- diagnostics.recovery_actions::build_recovery_actions (POS: Recovery action catalogue of the diagnostics engine)
- diagnostics.transport_diagnosis::diagnose_transport, infer_service_name (POS: TLS and connection diagnostics)
- diagnostics.types::DiagnosticResult, ErrorContext (POS: Error diagnostic data structures)
- core.security.redact::redact_sensitive_text (POS: Secret redaction of text shown to users and logs)
- toolkits.llms.errors.classifier::ErrorKind, classify_error (POS: LLM error classifier for failover decisions)

[OUTPUT]
- LLMErrorDiagnostic: Static classifier that maps LLM exceptions to localized DiagnosticResult

[POS]
LLM error diagnostic engine. Classifies exceptions from LLM calls into actionable categories
with localized user messages and resolution steps. Transport and account failures are diagnosed by
their own modules and tried first; the model, rate-limit, response-format, context and timeout
families, the provider failures the shared classifier recognizes (overload, safety filter, rejected request, WAF
challenge), the unknown fallback and the truncation diagnoses live here.
"""

import html
import re
from dataclasses import replace

from myrm_agent_harness.agent.errors.diagnostics.account_diagnosis import diagnose_account
from myrm_agent_harness.agent.errors.diagnostics.catalog_result import build_catalog_result
from myrm_agent_harness.agent.errors.diagnostics.cooldown_hint import format_cooldown_hint
from myrm_agent_harness.agent.errors.diagnostics.i18n import get_locale_manager
from myrm_agent_harness.agent.errors.diagnostics.recovery_actions import build_recovery_actions
from myrm_agent_harness.agent.errors.diagnostics.transport_diagnosis import diagnose_transport, infer_service_name
from myrm_agent_harness.agent.errors.diagnostics.types import (
    DiagnosticResult,
    ErrorContext,
)
from myrm_agent_harness.core.security.redact import redact_sensitive_text
from myrm_agent_harness.toolkits.llms.errors.classifier import ErrorKind, classify_error

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

# Provider failures the shared classifier recognizes by status code and provider wording: each reads
# from its own catalogue entry instead of the raw exception text.
_PROVIDER_KIND_TYPES: dict[ErrorKind, str] = {
    ErrorKind.OVERLOADED: "overloaded",
    ErrorKind.SAFETY_BLOCK: "safety_block",
    ErrorKind.FORMAT_ERROR: "format_error",
    ErrorKind.CHALLENGE_BLOCKED: "challenge_blocked",
}

# Client-library framing in front of the provider's words: litellm's exception class, the provider tag it adds
# ("OpenAIException - ", "AzureException BadRequestError - ") and the OpenAI SDK's status line ("Error code: 400 - ").
_LLM_LIBRARY_PREFIX = re.compile(
    r"^(?:litellm\.[A-Za-z]+Error:\s*)*"
    r"(?:[A-Za-z]+Exception(?:\s+[A-Za-z]+Error)?\s+-\s+)?"
    r"(?:Error code:\s*\d{3}\s+-\s+)?"
)
# The human sentence inside a JSON or Python-dict error body: `{"error": {"message": "..."}}`. Each quote style
# has its own branch and an escape pair never overlaps a plain character, so a body cut off mid-string fails in
# linear time instead of retrying every way to split a run of backslashes.
_MESSAGE_FIELD = re.compile(
    r"""["']message["']\s*:\s*(?:"(?P<double>(?:\\.|[^"\\])*)"|'(?P<single>(?:\\.|[^'\\])*)')""", re.DOTALL
)
_ESCAPE = re.compile(r"\\(.)")
_HTML_DOCUMENT = re.compile(r"<\s*(?:!doctype|html|head|body)\b", re.IGNORECASE)
_HTML_NON_TEXT = re.compile(r"<(script|style)\b.*?(?:</\1\s*>|$)", re.IGNORECASE | re.DOTALL)
_HTML_TAG = re.compile(r"<[^>]*>")
# Bounds the work done on a provider page; the shown text is cut to _MAX_ERROR_MESSAGE_CHARS afterwards.
_MAX_ERROR_SOURCE_CHARS = 2000
_MAX_ERROR_MESSAGE_CHARS = 200


def _unescape(text: str) -> str:
    return _ESCAPE.sub(lambda match: " " if match.group(1) == "n" else match.group(1), text)


def _provider_message(exc: Exception) -> str:
    """The provider's own words as one clean line: no client-library framing, body markup, page tags or secrets.

    Redaction runs before the cut so a credential is never left half-shown at the boundary.
    """
    text = str(exc)[:_MAX_ERROR_SOURCE_CHARS]
    body_message = _MESSAGE_FIELD.search(text)
    if body_message:
        quoted = body_message.group("double")
        text = _unescape(quoted if quoted is not None else body_message.group("single"))
    else:
        text = _LLM_LIBRARY_PREFIX.sub("", text)
    if _HTML_DOCUMENT.search(text):
        text = html.unescape(_HTML_TAG.sub(" ", _HTML_NON_TEXT.sub(" ", text)))
    text = " ".join(redact_sensitive_text(text).split())
    return text[:_MAX_ERROR_MESSAGE_CHARS] or type(exc).__name__


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

        full_text = f"{str(exc).lower()} {repr(exc).lower()}"

        # 0-3. Transport (TLS, connection) then account (billing, provider policy, API key) families
        transport = diagnose_transport(full_text, context, locale, cooldown_remaining_ms)
        if transport is not None:
            return transport

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

        # 9. Provider failures only the shared classifier recognizes
        provider_type = _PROVIDER_KIND_TYPES.get(classify_error(exc))
        if provider_type is not None:
            return build_catalog_result(
                provider_type, locale, cooldown_remaining_ms, error_message=_provider_message(exc)
            )

        # 10. Generic fallback
        return build_catalog_result("unknown", locale, cooldown_remaining_ms, error_message=_provider_message(exc))

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
