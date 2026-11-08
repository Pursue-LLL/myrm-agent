"""The embedding live probe grades a never-configured embedding as optional and a broken one as a fault."""

from __future__ import annotations

from collections.abc import Sequence

import httpx
import pytest
from myrm_agent_harness.api.config import ConfigIncompleteError
from myrm_agent_harness.toolkits.retriever.embedding.factory import EmbeddingConfig

from app.services.memory.diagnostics.diagnostic.diagnostic_live_probes import run_embedding_live_probe
from app.services.memory.diagnostics.diagnostic.diagnostic_probe_results import KEYWORD_MODE_EVIDENCE
from app.services.memory.shared_context import shared_context_health as health_module
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


def _configure(monkeypatch: pytest.MonkeyPatch, config: EmbeddingConfig) -> None:
    async def _cfg() -> EmbeddingConfig:
        return config

    monkeypatch.setattr(health_module, "require_platform_embedding_config", _cfg)


@pytest.mark.asyncio
async def test_embedding_live_probe_is_missing_when_embedding_was_never_configured(
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

    probe = await run_embedding_live_probe()

    assert probe.status == "missing"
    assert probe.evidence == KEYWORD_MODE_EVIDENCE
    assert probe.repair_actions == ["configure_embedding"]


@pytest.mark.asyncio
async def test_embedding_live_probe_stays_critical_for_a_placeholder_key(monkeypatch: pytest.MonkeyPatch) -> None:
    _configure(monkeypatch, EmbeddingConfig(model="text-embedding-3-small", api_key="changeme", api_base=None))

    probe = await run_embedding_live_probe()

    assert probe.status == "critical"
    assert "placeholder_embedding_api_key" in probe.evidence
    assert probe.repair_actions == ["configure_embedding"]


@pytest.mark.asyncio
async def test_embedding_live_probe_stays_critical_when_the_provider_rejects_the_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure(monkeypatch, EmbeddingConfig(model="text-embedding-3-small", api_key="sk-invalid", api_base=None))
    monkeypatch.setattr(
        health_module,
        "get_embedding_service",
        lambda config: _FakeEmbeddingService(
            exc=provider_failure(401, "Incorrect API key provided: sk-invalid", path="/v1/embeddings")
        ),
    )

    probe = await run_embedding_live_probe()

    assert probe.status == "critical"
    assert "invalid_api_key" in probe.evidence
    assert probe.repair_actions == ["configure_embedding"]


@pytest.mark.asyncio
async def test_embedding_live_probe_stays_critical_when_the_provider_is_unreachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure(monkeypatch, EmbeddingConfig(model="nomic-embed-text", api_key="default", api_base="http://127.0.0.1:11434/v1"))
    monkeypatch.setattr(
        health_module,
        "get_embedding_service",
        lambda config: _FakeEmbeddingService(exc=httpx.ConnectError("All connection attempts failed")),
    )

    probe = await run_embedding_live_probe()

    assert probe.status == "critical"
    assert "network_error" in probe.evidence
    assert probe.repair_actions == ["configure_embedding", "run_diagnostics"]


@pytest.mark.asyncio
async def test_embedding_live_probe_is_ready_when_the_provider_answers(monkeypatch: pytest.MonkeyPatch) -> None:
    _configure(monkeypatch, EmbeddingConfig(model="text-embedding-3-small", api_key="sk-valid", api_base=None))
    monkeypatch.setattr(health_module, "get_embedding_service", lambda config: _FakeEmbeddingService([0.1, 0.2]))

    probe = await run_embedding_live_probe()

    assert probe.status == "ready"
    assert probe.repair_actions == []
    assert probe.next_action == "No action required."
