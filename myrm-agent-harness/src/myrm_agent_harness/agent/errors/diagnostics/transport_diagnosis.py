"""TLS and connection diagnostics of the LLM error engine.

[INPUT]
- diagnostics.catalog_result::build_catalog_result (POS: DiagnosticResult assembly from the locale catalogue)
- diagnostics.types::DiagnosticResult, ErrorContext (POS: Error diagnostic data structures)
- infra.tls_compat::is_tls_transient_error (POS: Enterprise TLS compatibility)
- toolkits.llms.errors.tls_rejection::CONNECTION_KEYWORDS, rejects_certificate (POS: The one verdict on a rejected certificate)

[OUTPUT]
- diagnose_transport: maps a TLS or connection failure to a localized DiagnosticResult, None for any other error
- infer_service_name: names the local LLM service behind a custom endpoint URL
- extract_port: reads the port out of a custom endpoint URL

[POS]
Transport half of the diagnostic engine: errors where the request never reached a model (certificate
rejected, handshake interrupted, endpoint unreachable). The engine calls it first; every later family
assumes the request got through. Whether a certificate was rejected is the classifier's verdict too
(``rejects_certificate``), so the card and the retry, key and failover decisions always name the same cause.
"""

import re

from myrm_agent_harness.agent.errors.diagnostics.catalog_result import build_catalog_result
from myrm_agent_harness.agent.errors.diagnostics.types import DiagnosticResult, ErrorContext
from myrm_agent_harness.infra.tls_compat import is_tls_transient_error
from myrm_agent_harness.toolkits.llms.errors.tls_rejection import CONNECTION_KEYWORDS, rejects_certificate


def diagnose_transport(
    exc: Exception,
    full_text: str,
    context: ErrorContext | None,
    locale: str,
    cooldown_remaining_ms: int | None,
) -> DiagnosticResult | None:
    """Diagnose TLS and connection failures in priority order; None when the error is neither."""
    # 0. TLS/SSL errors: a rejected certificate (fail-fast) vs transient handshake
    # interruption (retryable). A rejection wins, wherever the client library put it:
    # a certificate can never verify by retrying.
    if rejects_certificate(exc, full_text):
        # No wait to announce: the provider's cooldown belongs to a rate limit, not to a rejected certificate.
        return build_catalog_result("tls_certificate", locale)

    if is_tls_transient_error(full_text):
        return build_catalog_result("tls_transient", locale, cooldown_remaining_ms)

    # 1. Connection errors (精准自定义端点诊断)
    if any(kw in full_text for kw in CONNECTION_KEYWORDS):
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
