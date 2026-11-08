"""extract_retrieval_models: the settings page's retrieval block becomes the configs the embedding and rerank factories take."""

from __future__ import annotations

import pytest

from app.core.channel_bridge.config_parsers.retrieval import extract_retrieval_models


def _settings(**changes: object) -> dict[str, object]:
    return {
        "embeddingApplied": True,
        "embeddingConfig": {"provider": "openai", "model": "text-embedding-3-small", "apiKey": "sk-embed"},
        "rerankerApplied": True,
        "rerankerConfig": {"provider": "cohere", "model": "rerank-v3.5", "apiKey": "sk-rerank"},
        **changes,
    }


def test_applied_settings_become_routed_configs() -> None:
    embedding, reranker = extract_retrieval_models(_settings())

    assert embedding is not None and reranker is not None
    assert (embedding.model, embedding.api_key, embedding.api_base) == ("openai/text-embedding-3-small", "sk-embed", None)
    assert (reranker.model, reranker.api_key, reranker.api_base) == ("cohere/rerank-v3.5", "sk-rerank", None)


def test_siliconflow_is_an_openai_compatible_endpoint_with_its_own_default_base() -> None:
    config = {"provider": "siliconflow", "model": "BAAI/bge-m3", "apiKey": "sk-sf"}

    embedding, _ = extract_retrieval_models(_settings(embeddingConfig=config))

    assert embedding is not None
    assert (embedding.model, embedding.api_base) == ("openai/BAAI/bge-m3", "https://api.siliconflow.cn/v1")


def test_an_endpoint_the_user_set_wins_over_the_providers_default() -> None:
    config = {"provider": "siliconflow", "model": "BAAI/bge-m3", "apiKey": "sk-sf", "apiBase": "http://localhost:8000/v1"}

    embedding, _ = extract_retrieval_models(_settings(embeddingConfig=config))

    assert embedding is not None
    assert embedding.api_base == "http://localhost:8000/v1"


@pytest.mark.parametrize(
    "changes",
    [
        pytest.param({"embeddingApplied": False}, id="not-applied"),
        pytest.param({"embeddingConfig": {"provider": "openai", "model": "m"}}, id="no-key"),
        pytest.param({"embeddingConfig": {"provider": "openai", "model": "", "apiKey": "k"}}, id="no-model"),
        pytest.param({"embeddingConfig": "not-a-block"}, id="not-a-block"),
    ],
)
def test_an_embedding_that_is_unapplied_or_incomplete_is_left_out_and_the_reranker_stays(
    changes: dict[str, object],
) -> None:
    embedding, reranker = extract_retrieval_models(_settings(**changes))

    assert embedding is None
    assert reranker is not None


@pytest.mark.parametrize("settings", [None, {}])
def test_no_retrieval_settings_is_no_configs(settings: dict[str, object] | None) -> None:
    assert extract_retrieval_models(settings) == (None, None)
