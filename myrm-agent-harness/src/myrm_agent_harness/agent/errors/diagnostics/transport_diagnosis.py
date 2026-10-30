"""TLS and connection diagnostics of the LLM error engine.

[INPUT]
- diagnostics.catalog_result::build_catalog_result (POS: DiagnosticResult assembly from the locale catalogue)
- diagnostics.cooldown_hint::format_cooldown_hint (POS: Cooldown hint rendering for rate-limit diagnostics)
- diagnostics.i18n::get_locale_manager (POS: Framework-level i18n for LLM error diagnostics)
- diagnostics.types::DiagnosticResult, ErrorContext (POS: Error diagnostic data structures)
- infra.tls_compat::is_tls_hard_error, is_tls_strict_error, is_tls_transient_error, get_tls_remediation_hint (POS: Enterprise TLS compatibility)

[OUTPUT]
- diagnose_transport: maps a TLS or connection failure to a localized DiagnosticResult, None for any other error
- infer_service_name: names the local LLM service behind a custom endpoint URL
- extract_port: reads the port out of a custom endpoint URL

[POS]
Transport half of the diagnostic engine: errors where the request never reached a model (certificate
rejected, handshake interrupted, endpoint unreachable). The engine calls it first; every later family
assumes the request got through.
"""

import re

from myrm_agent_harness.agent.errors.diagnostics.catalog_result import build_catalog_result
from myrm_agent_harness.agent.errors.diagnostics.cooldown_hint import format_cooldown_hint
from myrm_agent_harness.agent.errors.diagnostics.i18n import get_locale_manager
from myrm_agent_harness.agent.errors.diagnostics.types import DiagnosticResult, ErrorContext
from myrm_agent_harness.infra.tls_compat import (
    get_tls_remediation_hint,
    is_tls_hard_error,
    is_tls_strict_error,
    is_tls_transient_error,
)

_CONNECTION_KEYWORDS = (
    "connection refused",
    "connection reset",
    "connection error",
    "failed to establish",
)


def diagnose_transport(
    full_text: str,
    context: ErrorContext | None,
    locale: str,
    cooldown_remaining_ms: int | None,
) -> DiagnosticResult | None:
    """Diagnose TLS and connection failures in priority order; None when the error is neither."""
    locale_manager = get_locale_manager()

    # 0. TLS/SSL errors: hard failure (fail-fast) vs transient handshake
    # interruption (retryable). Hard signals win: a rejected certificate
    # can never verify by retrying.
    if is_tls_hard_error(full_text) or is_tls_strict_error(full_text):
        hint = get_tls_remediation_hint()
        raw_msg = locale_manager.translate("tls_certificate", "user_message", locale)
        raw_steps = locale_manager.translate("tls_certificate", "resolution_steps", locale)
        user_message = (
            raw_msg
            if isinstance(raw_msg, str) and not raw_msg.startswith("[Missing")
            else f"TLS certificate verification failed. {hint}"
        )
        steps: list[str] = raw_steps if isinstance(raw_steps, list) and raw_steps else [hint]

        return DiagnosticResult(
            error_type="tls_certificate",
            user_message=user_message,
            resolution_steps=steps,
            locale=locale,
        )

    if is_tls_transient_error(full_text):
        raw_msg = locale_manager.translate("tls_transient", "user_message", locale)
        raw_steps = locale_manager.translate("tls_transient", "resolution_steps", locale)
        fallback_msg = "TLS handshake interrupted — likely a temporary network problem."
        user_message = raw_msg if isinstance(raw_msg, str) and not raw_msg.startswith("[Missing") else fallback_msg
        steps = raw_steps if isinstance(raw_steps, list) and raw_steps else [fallback_msg]

        return DiagnosticResult(
            error_type="tls_transient",
            user_message=user_message + format_cooldown_hint(cooldown_remaining_ms, locale),
            resolution_steps=steps,
            locale=locale,
        )

    # 1. Connection errors (精准自定义端点诊断)
    if any(kw in full_text for kw in _CONNECTION_KEYWORDS):
        # 自定义端点(Ollama/LM Studio)专属诊断
        if context and context.is_custom_endpoint:
            return build_catalog_result(
                "custom_endpoint_unreachable",
                locale,
                cooldown_remaining_ms,
                service_name=infer_service_name(context.base_url),
                base_url_display=context.base_url or "custom endpoint",
                port=extract_port(context.base_url),
            )

        # 通用连接错误诊断
        return build_catalog_result("connection", locale, cooldown_remaining_ms)

    return None


def infer_service_name(base_url: str | None) -> str:
    """推断服务名称(Ollama/LM Studio/vLLM/自定义LLM服务)"""
    if not base_url:
        return "custom LLM service"

    base_url_lower = base_url.lower()

    if "11434" in base_url_lower:
        return "Ollama"
    elif "1234" in base_url_lower:
        return "LM Studio"
    elif "vllm" in base_url_lower:
        return "vLLM"
    else:
        return "custom LLM service"


def extract_port(base_url: str | None) -> str:
    """提取端口号"""
    if not base_url:
        return "unknown"

    port_match = re.search(r":(\d+)", base_url)
    return port_match.group(1) if port_match else "unknown"
