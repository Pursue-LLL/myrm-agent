from __future__ import annotations

from collections.abc import Sequence

import pytest
from myrm_agent_harness.toolkits.retriever.embedding.factory import EmbeddingConfig

from app.services.memory import shared_context_health as health_module


class _FakeEmbeddingService:
    def __init__(self, vector: Sequence[float] | None = None, exc: Exception | None = None) -> None:
        self._vector = list(vector or [0.1, 0.2, 0.3])
        self._exc = exc

    async def embed(self, text: str) -> list[float]:
        assert text
        if self._exc is not None:
            raise self._exc
        return self._vector


class AuthenticationError(Exception):
    """LiteLLM-compatible authentication failure name."""


async def _make_config(model: str, api_key: str, api_base: str | None) -> EmbeddingConfig:
    return EmbeddingConfig(model=model, api_key=api_key, api_base=api_base)


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
        return EmbeddingConfig(model="openai/local-embedding", api_key="default", api_base="http://127.0.0.1:11434/v1")

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
        lambda config: _FakeEmbeddingService(exc=AuthenticationError("Incorrect API key provided: sk-invalid")),
    )

    result = await health_module.check_shared_context_memory_health(probe=True)

    assert result.ready is False
    assert result.status == "not_configured"
    assert result.probed is True
    assert result.reason == "invalid_api_key"
    assert result.retryable is False
