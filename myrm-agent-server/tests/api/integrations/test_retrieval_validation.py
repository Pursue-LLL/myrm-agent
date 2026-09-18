"""Retrieval-config validation endpoints must always call the upstream provider.

These endpoints used to answer ``success=True`` for one hardcoded api_key without
touching the network, which silently reported "configuration valid" for a
credential whose upstream balance was exhausted. The regression guard below pins
the real-call contract so a validation result can never again be faked.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="integrations")

_DEAD_CREDENTIAL = "sk-nznibczsofctvcsavtubpsgtyhqxijdsspzcvwypkouawunz"


@pytest.fixture
def client() -> Iterator[TestClient]:
    """TestClient with auth bypassed via loopback IP mock."""
    with patch(
        "app.core.security.auth.identity.is_loopback_ip",
        return_value=True,
    ):
        yield TestClient(app)


class _StubEmbedding:
    """Stand-in for CloudEmbedding that records the api_key it was constructed with."""

    created_with: list[str] = []

    def __init__(self, model: str, api_key: str, api_base: str | None = None) -> None:
        type(self).created_with.append(api_key)

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [[0.0] * 4]


class _StubReranker:
    """Stand-in for CloudReranker that records the api_key it was constructed with."""

    created_with: list[str] = []

    def __init__(self, model: str, api_key: str, api_base: str | None = None) -> None:
        type(self).created_with.append(api_key)

    async def rerank(
        self,
        query: str,
        documents: list[str],
        top_k: int | None = None,
    ) -> list[Any]:
        return [type("R", (), {"index": 0, "score": 0.9, "text": documents[0]})()]


class TestEmbeddingValidationCallsUpstream:
    """POST /integrations/retrieval/embedding must delegate to the real service."""

    def test_arbitrary_key_reaches_embedding_service(self, client: TestClient) -> None:
        _StubEmbedding.created_with.clear()
        with patch(
            "myrm_agent_harness.toolkits.retriever.embedding.cloud_embedding.CloudEmbedding",
            _StubEmbedding,
        ):
            response = client.post(
                "/api/v1/integrations/retrieval/embedding",
                json={
                    "model": "BAAI/bge-m3",
                    "api_key": _DEAD_CREDENTIAL,
                    "api_base": "https://api.siliconflow.cn/v1",
                },
            )
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["message"] == "Validation successful (dimension: 4)"
        assert _StubEmbedding.created_with == [_DEAD_CREDENTIAL]

    def test_upstream_error_is_reported_not_swallowed(self, client: TestClient) -> None:
        class _FailingEmbedding:
            def __init__(self, model: str, api_key: str, api_base: str | None = None) -> None:
                self.api_key = api_key

            async def embed_batch(self, texts: list[str]) -> list[list[float]]:
                raise RuntimeError("account balance is insufficient")

        with patch(
            "myrm_agent_harness.toolkits.retriever.embedding.cloud_embedding.CloudEmbedding",
            _FailingEmbedding,
        ):
            response = client.post(
                "/api/v1/integrations/retrieval/embedding",
                json={
                    "model": "BAAI/bge-m3",
                    "api_key": _DEAD_CREDENTIAL,
                    "api_base": "https://api.siliconflow.cn/v1",
                },
            )
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is False
        assert "insufficient" in (body["error"] or "")


class TestRerankerValidationCallsUpstream:
    """POST /integrations/retrieval/reranker must delegate to the real service."""

    def test_arbitrary_key_reaches_reranker_service(self, client: TestClient) -> None:
        _StubReranker.created_with.clear()
        with patch(
            "myrm_agent_harness.toolkits.retriever.reranker.cloud_reranker.CloudReranker",
            _StubReranker,
        ):
            response = client.post(
                "/api/v1/integrations/retrieval/reranker",
                json={
                    "model": "BAAI/bge-reranker-v2-m3",
                    "api_key": _DEAD_CREDENTIAL,
                    "api_base": "https://api.siliconflow.cn/v1",
                },
            )
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["message"] == "Validation successful (returned 1 result)"
        assert _StubReranker.created_with == [_DEAD_CREDENTIAL]
