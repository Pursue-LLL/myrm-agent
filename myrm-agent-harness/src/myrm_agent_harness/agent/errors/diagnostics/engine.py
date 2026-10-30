"""LLM error diagnostic engine.

[INPUT]
- diagnostics.account_diagnosis::diagnose_account (POS: Billing, provider-policy and API key diagnostics)
- diagnostics.i18n::get_locale_manager (POS: Framework-level i18n for LLM error diagnostics)
- diagnostics.recovery_actions::build_recovery_actions (POS: Recovery action catalogue of the diagnostics engine)
- diagnostics.transport_diagnosis::diagnose_transport, infer_service_name (POS: TLS and connection diagnostics)
- diagnostics.types::DiagnosticResult, ErrorContext (POS: Error diagnostic data structures)

[OUTPUT]
- LLMErrorDiagnostic: Static classifier that maps LLM exceptions to localized DiagnosticResult

[POS]
LLM error diagnostic engine. Classifies exceptions from LLM calls into actionable categories
with localized user messages and resolution steps. Transport and account failures are diagnosed by
their own modules and tried first; the model, rate-limit, response-format, context, timeout and
unknown families, the truncation diagnoses and the cooldown wrapper live here.
"""

import re

from myrm_agent_harness.agent.errors.diagnostics.account_diagnosis import diagnose_account
from myrm_agent_harness.agent.errors.diagnostics.i18n import get_locale_manager
from myrm_agent_harness.agent.errors.diagnostics.recovery_actions import build_recovery_actions
from myrm_agent_harness.agent.errors.diagnostics.transport_diagnosis import diagnose_transport, infer_service_name
from myrm_agent_harness.agent.errors.diagnostics.types import (
    DiagnosticResult,
    ErrorContext,
)


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
        locale_manager = get_locale_manager()
        if locale is None:
            locale = locale_manager.detect_locale()

        error_str = str(exc).lower()
        error_repr = repr(exc).lower()
        full_text = f"{error_str} {error_repr}"

        # 0-3. Transport (TLS, connection) then account (billing, provider policy, API key) families
        transport = diagnose_transport(full_text, context, locale, cooldown_remaining_ms)
        if transport is not None:
            return transport

        account = diagnose_account(exc, full_text, locale, cooldown_remaining_ms)
        if account is not None:
            return account

        # 4. Model not found (精准自定义端点诊断)
        model_keywords = ["model not found", "model does not exist", "unknown model"]
        if (
            any(kw in full_text for kw in model_keywords)
            or re.search(r"(?<!\d)404(?!\d)", full_text)
            or ("model" in full_text and "not found" in full_text)
        ):
            if context and context.model_name:
                model_name = context.model_name
            else:
                model_match = re.search(r"model[:\s]+([a-zA-Z0-9\-._/]+)", full_text)
                model_name = model_match.group(1) if model_match else "unknown"

            # 自定义端点(Ollama/LM Studio)专属诊断
            if context and context.is_custom_endpoint:
                service_name = infer_service_name(context.base_url)
                params = {"model_name": model_name, "service_name": service_name}

                user_message = locale_manager.translate("custom_model_not_found", "user_message", locale, **params)
                resolution_steps = locale_manager.translate(
                    "custom_model_not_found", "resolution_steps", locale, **params
                )

                cooldown_hint = LLMErrorDiagnostic._format_cooldown_hint(cooldown_remaining_ms, locale)
                user_message += cooldown_hint

                return DiagnosticResult(
                    error_type="custom_model_not_found",
                    user_message=user_message,
                    resolution_steps=resolution_steps,
                    is_retryable=False,
                    locale=locale,
                )

            # 通用模型未找到诊断
            params = {"model_name": model_name}
            user_message = locale_manager.translate("model", "user_message", locale, **params)
            resolution_steps = locale_manager.translate("model", "resolution_steps", locale, **params)

            cooldown_hint = LLMErrorDiagnostic._format_cooldown_hint(cooldown_remaining_ms, locale)
            user_message += cooldown_hint

            return DiagnosticResult(
                error_type="model",
                user_message=user_message,
                resolution_steps=resolution_steps,
                is_retryable=True,
                locale=locale,
            )

        # 5. Rate limit
        rate_limit_keywords = ["rate limit", "too many requests", "quota exceeded"]
        if any(kw in full_text for kw in rate_limit_keywords) or re.search(r"(?<!\d)429(?!\d)", full_text):
            user_message = locale_manager.translate("rate_limit", "user_message", locale)
            resolution_steps = locale_manager.translate("rate_limit", "resolution_steps", locale)

            cooldown_hint = LLMErrorDiagnostic._format_cooldown_hint(cooldown_remaining_ms, locale)
            user_message += cooldown_hint
            # A known wait is already in the message; a second, different one would contradict it.
            wait_step = None if cooldown_hint else locale_manager.translate_optional("rate_limit", "wait_step", locale)
            if wait_step:
                resolution_steps = [wait_step, *resolution_steps]

            return DiagnosticResult(
                error_type="rate_limit",
                user_message=user_message,
                resolution_steps=resolution_steps,
                is_retryable=True,
                locale=locale,
            )

        # 6. Response format error
        if any(
            kw in full_text
            for kw in [
                "must be in json format",
                "schema validation error",
                "invalid json format",
                "malformed json",
            ]
        ):
            user_message = locale_manager.translate("response_format_error", "user_message", locale)
            resolution_steps = locale_manager.translate("response_format_error", "resolution_steps", locale)

            cooldown_hint = LLMErrorDiagnostic._format_cooldown_hint(cooldown_remaining_ms, locale)
            user_message += cooldown_hint

            return DiagnosticResult(
                error_type="response_format_error",
                user_message=user_message,
                resolution_steps=resolution_steps,
                is_retryable=True,
                locale=locale,
            )

        # 7. Context overflow
        if any(
            kw in full_text
            for kw in [
                "context length",
                "token limit",
                "context window",
                "too long",
                "max tokens",
            ]
        ):
            user_message = locale_manager.translate("context_overflow", "user_message", locale)
            resolution_steps = locale_manager.translate("context_overflow", "resolution_steps", locale)

            cooldown_hint = LLMErrorDiagnostic._format_cooldown_hint(cooldown_remaining_ms, locale)
            user_message += cooldown_hint

            return DiagnosticResult(
                error_type="context_overflow",
                user_message=user_message,
                resolution_steps=resolution_steps,
                is_retryable=True,
                locale=locale,
            )

        # 8. Timeout
        if any(kw in full_text for kw in ["timeout", "timed out", "time out"]):
            user_message = locale_manager.translate("timeout", "user_message", locale)
            resolution_steps = locale_manager.translate("timeout", "resolution_steps", locale)

            cooldown_hint = LLMErrorDiagnostic._format_cooldown_hint(cooldown_remaining_ms, locale)
            user_message += cooldown_hint

            return DiagnosticResult(
                error_type="timeout",
                user_message=user_message,
                resolution_steps=resolution_steps,
                is_retryable=True,
                locale=locale,
            )

        # 9. Generic fallback
        params = {"error_message": str(exc)[:200]}
        user_message = locale_manager.translate("unknown", "user_message", locale, **params)
        resolution_steps = locale_manager.translate("unknown", "resolution_steps", locale)

        cooldown_hint = LLMErrorDiagnostic._format_cooldown_hint(cooldown_remaining_ms, locale)
        user_message += cooldown_hint

        return DiagnosticResult(
            error_type="unknown",
            user_message=user_message,
            resolution_steps=resolution_steps,
            is_retryable=False,
            locale=locale,
        )

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
        locale_manager = get_locale_manager()
        if locale is None:
            locale = locale_manager.detect_locale()

        user_message = locale_manager.translate(truncation_type, "user_message", locale)
        resolution_steps = locale_manager.translate(truncation_type, "resolution_steps", locale)

        return DiagnosticResult(
            error_type=truncation_type,
            user_message=user_message,
            resolution_steps=resolution_steps,
            is_retryable=False,
            locale=locale,
        )

    @staticmethod
    def get_recovery_actions(error_type: str, locale: str | None = "en") -> list[dict[str, str]]:
        """Return localized actionable recovery buttons for the given error type."""
        return build_recovery_actions(error_type, locale)

    @staticmethod
    def _format_cooldown_hint(cooldown_remaining_ms: int | None, locale: str) -> str:
        """生成cooldown提示(如果存在)"""
        from myrm_agent_harness.agent.errors.diagnostics.cooldown_hint import format_cooldown_hint

        return format_cooldown_hint(cooldown_remaining_ms, locale)
