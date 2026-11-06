from __future__ import annotations

from collections.abc import Sequence

import httpx
import pytest
from myrm_agent_harness.api.config import ConfigIncompleteError
from myrm_agent_harness.toolkits.retriever.embedding.factory import EmbeddingConfig

from app.services.memory.shared_context import shared_context_health as health_module
from tests.support.fake_retrieval_provider import FakeRetrievalProvider, fake_retrieval_provider
from tests.support.provider_failures import provider_failure


class _FakeEmbeddingService:
    def __init__(self, vector: Sequence[float] | None = None, exc: Exception | None = None) -> None:
        self._vector = list(vector or [0.1, 0.2, 0.3])
        self._exc = exc

    async def embed(self, text: str) -> list[float]:
        assert text
        if self._exc is not None:
            raise self._exc
        return self._vector


async def _make_config(model: str, api_key: str, api_base: str | None) -> EmbeddingConfig:
    return EmbeddingConfig(model=model, api_key=api_key, api_base=api_base)


@pytest.mark.asyncio
async def test_shared_context_health_degrades_when_embedding_is_not_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _cfg() -> EmbeddingConfig:
        raise ConfigIncompleteError(
            user_friendly_message={"en": "Embedding is not configured."},
            technical_details="missing embedding config",
            resolution_steps=["Configure an embedding provider"],
            error_code="embedding_not_configured",
        )

    monkeypatch.setattr(health_module, "require_platform_embedding_config", _cfg)

    result = await health_module.check_shared_context_memory_health(probe=True)

    assert result.ready is False
    assert result.status == "not_configured"
    assert result.model == ""
    assert result.probed is False
    assert result.reason == "embedding_not_configured"
    assert result.retryable is False


@pytest.mark.asyncio
async def test_shared_context_health_blocks_placeholder_cloud_key(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _cfg() -> EmbeddingConfig:
        return EmbeddingConfig(model="text-embedding-3-small", api_key="default", api_base=None)

    monkeypatch.setattr(health_module, "require_platform_embedding_config", _cfg)

    result = await health_module.check_shared_context_memory_health(probe=True)

    assert result.ready is False
    assert result.status == "not_configured"
    assert result.probed is False
    assert result.reason == "placeholder_embedding_api_key"
    assert result.retryable is False


@pytest.mark.asyncio
async def test_shared_context_health_allows_config_only_local_base(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _cfg() -> EmbeddingConfig:
        return EmbeddingConfig(model="nomic-embed-text", api_key="default", api_base="http://127.0.0.1:11434/v1")

    monkeypatch.setattr(health_module, "require_platform_embedding_config", _cfg)

    result = await health_module.check_shared_context_memory_health(probe=False)

    assert result.ready is True
    assert result.status == "ready"
    assert result.probed is False
    assert result.reason == "probe_skipped"
    assert result.api_key_configured is False


@pytest.mark.asyncio
async def test_shared_context_health_reports_probe_dimension(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _cfg() -> EmbeddingConfig:
        return EmbeddingConfig(model="text-embedding-3-small", api_key="sk-valid", api_base=None)

    monkeypatch.setattr(health_module, "require_platform_embedding_config", _cfg)
    monkeypatch.setattr(health_module, "get_embedding_service", lambda config: _FakeEmbeddingService([0.1, 0.2]))

    result = await health_module.check_shared_context_memory_health(probe=True)

    assert result.ready is True
    assert result.status == "ready"
    assert result.probed is True
    assert result.reason is None
    assert result.vector_dimension == 2


@pytest.mark.asyncio
async def test_shared_context_health_sanitizes_probe_auth_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _cfg() -> EmbeddingConfig:
        return EmbeddingConfig(model="text-embedding-3-small", api_key="sk-invalid", api_base=None)

    monkeypatch.setattr(health_module, "require_platform_embedding_config", _cfg)
    monkeypatch.setattr(
        health_module,
        "get_embedding_service",
        lambda config: _FakeEmbeddingService(
            exc=provider_failure(401, "Incorrect API key provided: sk-invalid", path="/v1/embeddings")
        ),
    )

    result = await health_module.check_shared_context_memory_health(probe=True)

    assert result.ready is False
    assert result.status == "not_configured"
    assert result.probed is True
    assert result.reason == "invalid_api_key"
    assert result.retryable is False


@pytest.mark.asyncio
async def test_shared_context_health_asks_the_provider_that_is_configured_now(monkeypatch: pytest.MonkeyPatch) -> None:
    """The real embedding client asks the configured provider on every probe; another provider's answer does not vouch for it."""

    async def probe(provider: FakeRetrievalProvider, api_key: str) -> health_module.SharedContextMemoryHealthResult:
        async def _cfg() -> EmbeddingConfig:
            return EmbeddingConfig(model="openai/test-embed", api_key=api_key, api_base=provider.api_base)

        monkeypatch.setattr(health_module, "require_platform_embedding_config", _cfg)
        return await health_module.check_shared_context_memory_health(probe=True)

    with fake_retrieval_provider() as accepting, fake_retrieval_provider() as refusing:
        refusing.status = 401
        accepted = await probe(accepting, "sk-right")
        refused = await probe(refusing, "sk-edited")

    assert (accepted.ready, accepted.reason) == (True, None)
    assert (refused.ready, refused.reason) == (False, "invalid_api_key")
    assert len(refusing.requests) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "refusal",
    [
        "Access denied due to invalid subscription key or wrong API endpoint",
        "invalid api token",
    ],
)
async def test_a_rejected_key_is_recognised_by_the_status_whatever_the_provider_calls_it(
    monkeypatch: pytest.MonkeyPatch, refusal: str
) -> None:
    """Azure and Cohere answer 401 without the words "api key": the status alone says the key was refused."""
    with fake_retrieval_provider() as provider:
        provider.status = 401
        provider.refusal = refusal

        async def _cfg() -> EmbeddingConfig:
            return EmbeddingConfig(model="openai/test-embed", api_key="sk-edited", api_base=provider.api_base)

        monkeypatch.setattr(health_module, "require_platform_embedding_config", _cfg)
        result = await health_module.check_shared_context_memory_health(probe=True)

    assert (result.ready, result.status, result.reason, result.retryable) == (False, "not_configured", "invalid_api_key", False)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("failure", "reason", "retryable"),
    [
        (provider_failure(402, "Request refused", path="/v1/embeddings"), "insufficient_quota", False),
        (provider_failure(408, "Request refused", path="/v1/embeddings"), "timeout", True),
        (provider_failure(429, "Request refused", path="/v1/embeddings"), "rate_limited", True),
        (provider_failure(503, "Request refused", path="/v1/embeddings"), "embedding_probe_failed", True),
        (httpx.ReadTimeout("provider stayed silent"), "timeout", True),
        (httpx.ConnectError("All connection attempts failed"), "network_error", True),
    ],
    ids=["402", "408", "429", "503", "read-timeout", "connect-error"],
)
async def test_a_failed_probe_is_graded_by_the_status_or_the_transport_error(
    monkeypatch: pytest.MonkeyPatch, failure: Exception, reason: str, retryable: bool
) -> None:
    """The failures the embedding transport raises, with an answer body that carries none of the usual wording."""

    async def _cfg() -> EmbeddingConfig:
        return EmbeddingConfig(model="text-embedding-3-small", api_key="sk-valid", api_base=None)

    monkeypatch.setattr(health_module, "require_platform_embedding_config", _cfg)
    monkeypatch.setattr(health_module, "get_embedding_service", lambda config: _FakeEmbeddingService(exc=failure))

    result = await health_module.check_shared_context_memory_health(probe=True)

    assert (result.ready, result.status, result.reason, result.retryable) == (False, "unreachable", reason, retryable)
