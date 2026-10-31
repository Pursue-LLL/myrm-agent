"""TLS and connection diagnostics of the LLM error engine.

[INPUT]
- diagnostics.catalog_result::build_catalog_result (POS: DiagnosticResult assembly from the locale catalogue)
- diagnostics.types::DiagnosticResult, ErrorContext (POS: Error diagnostic data structures)
- infra.tls_compat::is_tls_hard_error, is_tls_transient_error (POS: Enterprise TLS compatibility)
- toolkits.llms.errors.error_payload::walk_exception_chain (POS: The one reader of the provider's answer in an LLM exception)

[OUTPUT]
- diagnose_transport: maps a TLS or connection failure to a localized DiagnosticResult, None for any other error;
  a connection failure whose cause names a rejected certificate is a TLS failure
- infer_service_name: names the local LLM service behind a custom endpoint URL
- extract_port: reads the port out of a custom endpoint URL

[POS]
Transport half of the diagnostic engine: errors where the request never reached a model (certificate
rejected, handshake interrupted, endpoint unreachable). The engine calls it first; every later family
assumes the request got through. A client library words a rejected certificate as a bare "Connection error."
and keeps the reason in the cause chain, so a connection failure is also read through its causes.
"""

import re

from myrm_agent_harness.agent.errors.diagnostics.catalog_result import build_catalog_result
from myrm_agent_harness.agent.errors.diagnostics.types import DiagnosticResult, ErrorContext
from myrm_agent_harness.infra.tls_compat import is_tls_hard_error, is_tls_transient_error
from myrm_agent_harness.toolkits.llms.errors.error_payload import walk_exception_chain

_CONNECTION_KEYWORDS = (
    "connection refused",
    "connection reset",
    "connection error",
    "failed to establish",
)


def _cause_rejects_certificate(exc: Exception) -> bool:
    """True when a cause wrapped by *exc* carries a hard TLS signal that the wrapper's own text lacks.

    Only hard signals are read through the chain. The transient ones include protocol-agnostic phrases
    ("wrong version number", "broken pipe"), which would turn an https URL pointed at a plain-HTTP service
    into a retry hint.
    """
    return any(is_tls_hard_error(str(cause)) for cause in walk_exception_chain(exc)[1:])


def diagnose_transport(
    exc: Exception,
    full_text: str,
    context: ErrorContext | None,
    locale: str,
    cooldown_remaining_ms: int | None,
) -> DiagnosticResult | None:
    """Diagnose TLS and connection failures in priority order; None when the error is neither."""
    # 0. TLS/SSL errors: hard failure (fail-fast) vs transient handshake
    # interruption (retryable). Hard signals win: a rejected certificate
    # can never verify by retrying.
    if is_tls_hard_error(full_text):
        # No wait to announce: the provider's cooldown belongs to a rate limit, not to a rejected certificate.
        return build_catalog_result("tls_certificate", locale)

    if is_tls_transient_error(full_text):
        return build_catalog_result("tls_transient", locale, cooldown_remaining_ms)

    # 1. Connection errors (精准自定义端点诊断)
    if any(kw in full_text for kw in _CONNECTION_KEYWORDS):
        # A wrapper's own text says only that the connection failed; a rejected certificate shows in its
        # causes, and no amount of checking the service, the network or the firewall fixes it.
        if _cause_rejects_certificate(exc):
            return build_catalog_result("tls_certificate", locale)

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
