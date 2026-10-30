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
- toolkits.llms.errors.error_payload::provider_error_message (POS: The one reader of the provider's answer in an LLM exception)

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
import json
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
from myrm_agent_harness.toolkits.llms.errors.error_payload import provider_error_message

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
    ErrorKind.CHALLENGE_BLOCKED: "challenge_blocked",
}

# Client-library framing in front of the provider's words: litellm's exception class, then the provider's own
# framing, the tag litellm adds ("OpenAIException - ", "AzureException BadRequestError - ") or the OpenAI SDK's
# status line ("Error code: 400 - "). The `provider` group is non-empty only when the provider's framing is present.
_LLM_LIBRARY_PREFIX = re.compile(
    r"^(?:litellm\.[A-Za-z]+Error:\s*)*"
    r"(?P<provider>(?:[A-Za-z]+Exception(?:\s+[A-Za-z]+Error)?\s+-\s+)?(?:Error code:\s*\d{3}\s+-\s+)?)"
)
# The human sentence inside a JSON or Python-dict error body: `{"error": {"message": "..."}}`. Each quote style
# has its own branch and an escape pair never overlaps a plain character, so a body cut off mid-string fails in
# linear time instead of retrying every way to split a run of backslashes.
_MESSAGE_FIELD = re.compile(
    r"""["']message["']\s*:\s*(?:"(?P<double>(?:\\.|[^"\\])*)"|'(?P<single>(?:\\.|[^'\\])*)')""", re.DOTALL
)
# The escapes of a Python dict repr: \xNN, \uNNNN, \UNNNNNNNN, or a backslash before any one character.
_ESCAPE = re.compile(r"\\(?:x([0-9a-fA-F]{2})|u([0-9a-fA-F]{4})|U([0-9a-fA-F]{8})|(.))", re.DOTALL)
_HTML_DOCUMENT = re.compile(r"<\s*(?:!doctype|html|head|body)\b", re.IGNORECASE)
_HTML_NON_TEXT = re.compile(r"<(script|style)\b.*?(?:</\1\s*>|$)", re.IGNORECASE | re.DOTALL)
_HTML_TAG = re.compile(r"<[^>]*>")
# Bounds the work done on a provider page; the shown text is cut to _MAX_ERROR_MESSAGE_CHARS afterwards.
_MAX_ERROR_SOURCE_CHARS = 2000
_MAX_ERROR_MESSAGE_CHARS = 200


def _unescape(text: str) -> str:
    """Decode the escapes of a Python-repr string; a code point that is not a character stays as written."""

    def decode(match: re.Match[str]) -> str:
        digits = match.group(1) or match.group(2) or match.group(3)
        if digits is None:
            return " " if match.group(4) in "nrt" else match.group(4)
        code = int(digits, 16)
        return chr(code) if code <= 0x10FFFF and not 0xD800 <= code <= 0xDFFF else match.group(0)

    return _ESCAPE.sub(decode, text)


def _unescape_json(text: str) -> str:
    """Decode the escapes of the inside of a JSON string, surrogate pairs included."""
    try:
        decoded = json.loads(f'"{text}"')
    except ValueError:
        return _unescape(text)
    return decoded if isinstance(decoded, str) else text


def _embedded_message(raw: str) -> str | None:
    """The provider's words inside exception text: a body's `message` field, the text after provider framing, or a page."""
    field = _MESSAGE_FIELD.search(raw)
    if field:
        double = field.group("double")
        return _unescape_json(double) if double is not None else _unescape(field.group("single"))
    prefix = _LLM_LIBRARY_PREFIX.match(raw)
    if prefix and prefix.group("provider"):
        return raw[prefix.end() :]
    return raw if _HTML_DOCUMENT.search(raw) else None


def _provider_words(exc: Exception, raw: str) -> str | None:
    """What the provider said, from its payload when the exception carries one, else from the exception text."""
    return provider_error_message(exc) or _embedded_message(raw)


def _present(text: str) -> str:
    """One line a user can read: page markup removed, secrets masked, whitespace collapsed, cut with an ellipsis.

    Redaction runs before the cut so a credential is never left half-shown at the boundary.
    """
    if _HTML_DOCUMENT.search(text):
        text = html.unescape(_HTML_TAG.sub(" ", _HTML_NON_TEXT.sub(" ", text)))
    text = " ".join(redact_sensitive_text(text).split())
    if len(text) <= _MAX_ERROR_MESSAGE_CHARS:
        return text
    return text[:_MAX_ERROR_MESSAGE_CHARS].rstrip() + "…"


def _provider_message(exc: Exception) -> str | None:
    """The provider's own words as one clean line, or ``None`` when the provider said nothing."""
    words = _provider_words(exc, str(exc)[:_MAX_ERROR_SOURCE_CHARS])
    return _present(words[:_MAX_ERROR_SOURCE_CHARS]) or None if words else None


def _error_text(exc: Exception) -> str:
    """The text of an unclassified failure as one clean line: the provider's words, else the exception's own text."""
    raw = str(exc)[:_MAX_ERROR_SOURCE_CHARS]
    words = _provider_words(exc, raw) or _LLM_LIBRARY_PREFIX.sub("", raw)
    return _present(words[:_MAX_ERROR_SOURCE_CHARS]) or type(exc).__name__


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
    message = _provider_message(exc)
    if message is not None:
        return build_catalog_result("format_error", locale, cooldown_remaining_ms, error_message=message)
    if context and context.model_name:
        return build_catalog_result(
            "format_error", locale, cooldown_remaining_ms, entry="format_error_model", model_name=context.model_name
        )
    return build_catalog_result("format_error", locale, cooldown_remaining_ms, entry="format_error_generic")


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
        kind = classify_error(exc)
        if kind is ErrorKind.FORMAT_ERROR:
            return _diagnose_rejected_request(exc, context, locale, cooldown_remaining_ms)
        provider_type = _PROVIDER_KIND_TYPES.get(kind)
        if provider_type is not None:
            return build_catalog_result(provider_type, locale, cooldown_remaining_ms)

        # 10. Generic fallback
        return build_catalog_result("unknown", locale, cooldown_remaining_ms, error_message=_error_text(exc))

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
