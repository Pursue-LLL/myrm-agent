"""Shared Context memory health service.

[INPUT]
myrm_agent_harness.toolkits.retriever.embedding.factory::EmbeddingConfig (POS: Embedding factory)
myrm_agent_harness.toolkits.retriever.embedding.factory::get_embedding_service (POS: Embedding factory)

[OUTPUT]
SharedContextMemoryHealthResult: Shared Context memory dependency health result
check_shared_context_memory_health: validates embedding configuration and optional live probe

[POS]
共享上下文记忆健康服务。为 API/UI/smoke 验证提供安全的 embedding 依赖预检，不暴露密钥或原始异常。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal
from urllib.parse import urlparse

from myrm_agent_harness.toolkits.retriever.embedding.factory import get_embedding_service

from app.services.agent.platform_config import require_platform_embedding_config

SharedContextMemoryHealthStatus = Literal["ready", "not_configured", "unreachable"]

_PLACEHOLDER_API_KEYS = {
    "",
    "default",
    "changeme",
    "change-me",
    "your-api-key",
    "your_api_key",
    "sk-xxx",
    "sk-xxxx",
    "sk-...",
}
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "0.0.0.0"}
_HEALTH_PROBE_TEXT = "shared context memory health check"


@dataclass(frozen=True)
class SharedContextMemoryHealthResult:
    """Safe Shared Context memory dependency health result."""

    ready: bool
    status: SharedContextMemoryHealthStatus
    model: str
    api_base_configured: bool
    api_key_configured: bool
    probed: bool
    reason: str | None
    retryable: bool
    checked_at: datetime
    vector_dimension: int | None = None


@dataclass(frozen=True)
class _ProbeFailure:
    status: SharedContextMemoryHealthStatus
    reason: str
    retryable: bool


def _is_placeholder_api_key(api_key: str | None) -> bool:
    return (api_key or "").strip().lower() in _PLACEHOLDER_API_KEYS


def _is_local_api_base(api_base: str | None) -> bool:
    if not api_base:
        return False
    parsed = urlparse(api_base)
    host = parsed.hostname or api_base.split(":", 1)[0]
    return host.lower() in _LOCAL_HOSTS


def _classify_probe_failure(exc: Exception) -> _ProbeFailure:
    name = type(exc).__name__.lower()
    message = str(exc).lower()
    combined = f"{name} {message}"
    if "authentication" in combined or "unauthorized" in combined or "incorrect api key" in combined:
        return _ProbeFailure(status="not_configured", reason="invalid_api_key", retryable=False)
    if "api key" in combined and ("invalid" in combined or "missing" in combined):
        return _ProbeFailure(status="not_configured", reason="invalid_api_key", retryable=False)
    if "quota" in combined or "insufficient" in combined:
        return _ProbeFailure(status="unreachable", reason="insufficient_quota", retryable=False)
    if "rate" in combined or "429" in combined:
        return _ProbeFailure(status="unreachable", reason="rate_limited", retryable=True)
    if "timeout" in combined or "timed out" in combined:
        return _ProbeFailure(status="unreachable", reason="timeout", retryable=True)
    if "connection" in combined or "network" in combined or "connect" in combined:
        return _ProbeFailure(status="unreachable", reason="network_error", retryable=True)
    return _ProbeFailure(status="unreachable", reason="embedding_probe_failed", retryable=True)


async def check_shared_context_memory_health(*, probe: bool) -> SharedContextMemoryHealthResult:
    """Check whether Shared Context memory materialization can use embeddings safely."""
    config = await require_platform_embedding_config()
    api_key_configured = not _is_placeholder_api_key(config.api_key)
    local_api_base = _is_local_api_base(config.api_base)
    checked_at = datetime.now(UTC)

    if not api_key_configured and not local_api_base:
        return SharedContextMemoryHealthResult(
            ready=False,
            status="not_configured",
            model=config.model,
            api_base_configured=bool(config.api_base),
            api_key_configured=False,
            probed=False,
            reason="missing_embedding_api_key" if config.api_key is None else "placeholder_embedding_api_key",
            retryable=False,
            checked_at=checked_at,
        )

    if not probe:
        return SharedContextMemoryHealthResult(
            ready=True,
            status="ready",
            model=config.model,
            api_base_configured=bool(config.api_base),
            api_key_configured=api_key_configured,
            probed=False,
            reason="probe_skipped",
            retryable=False,
            checked_at=checked_at,
        )

    try:
        vector = await get_embedding_service(config).embed(_HEALTH_PROBE_TEXT)
    except Exception as exc:
        failure = _classify_probe_failure(exc)
        return SharedContextMemoryHealthResult(
            ready=False,
            status=failure.status,
            model=config.model,
            api_base_configured=bool(config.api_base),
            api_key_configured=api_key_configured,
            probed=True,
            reason=failure.reason,
            retryable=failure.retryable,
            checked_at=checked_at,
        )

    return SharedContextMemoryHealthResult(
        ready=bool(vector),
        status="ready" if vector else "unreachable",
        model=config.model,
        api_base_configured=bool(config.api_base),
        api_key_configured=api_key_configured,
        probed=True,
        reason=None if vector else "empty_embedding_vector",
        retryable=not bool(vector),
        checked_at=checked_at,
        vector_dimension=len(vector) if vector else None,
    )
