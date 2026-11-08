"""Retrieval-config validation: POST /integrations/retrieval/{embedding,reranker} probe the real provider.

The real embedding and rerank clients run against a loopback provider, so what the endpoints report for a bad key, an
unknown model or an unreachable host comes from the exceptions those clients actually raise, not from stubs.
"""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from tests.support.fake_retrieval_provider import FakeRetrievalProvider, fake_retrieval_provider, unreachable_api_base
from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="integrations")

_MODELS = {"embedding": "openai/test-embed", "reranker": "openai/test-rerank"}
_PROVIDER_PATHS = {"embedding": "/v1/embeddings", "reranker": "/v1/rerank"}
_KINDS = ["embedding", "reranker"]


@pytest.fixture
def client() -> Iterator[TestClient]:
    with patch("app.core.security.auth.identity.is_loopback_ip", return_value=True):
        yield TestClient(app)


@pytest.fixture
def provider() -> Iterator[FakeRetrievalProvider]:
    with fake_retrieval_provider() as running:
        yield running


@pytest.fixture
def api_key() -> str:
    # The retriever factories keep one service per (model, key, base): a fresh key keeps every test on its own service.
    return f"sk-probe-{uuid4().hex}"


def _probe(client: TestClient, kind: str, *, api_key: str, api_base: str | None, model: str | None = None) -> dict[str, object]:
    response = client.post(
        f"/api/v1/integrations/retrieval/{kind}",
        json={"model": model or _MODELS[kind], "api_key": api_key, "api_base": api_base, "provider": "openai"},
    )
    # The settings UI reads success / message from a 200, also when the provider refuses the probe.
    assert response.status_code == 200, response.text
    body: dict[str, object] = response.json()
    return body


def test_embedding_probe_reports_the_dimension_the_provider_answered(
    client: TestClient, provider: FakeRetrievalProvider, api_key: str
) -> None:
    provider.dimension = 8

    result = _probe(client, "embedding", api_key=api_key, api_base=provider.api_base)

    assert result == {"success": True, "message": "Validation successful (dimension: 8)", "error": None}
    [seen] = provider.requests
    assert seen.path == "/v1/embeddings"
    assert seen.authorization == f"Bearer {api_key}"
    texts = seen.body["input"]
    assert isinstance(texts, list) and len(texts) == 1
    assert str(texts[0]).startswith("probe-")


@pytest.mark.parametrize(("hits", "noun"), [(1, "result"), (2, "results")])
def test_reranker_probe_reports_the_hits_the_provider_answered(
    client: TestClient, provider: FakeRetrievalProvider, api_key: str, hits: int, noun: str
) -> None:
    provider.rerank_results = [{"index": index, "relevance_score": 0.9 - index / 10} for index in range(hits)]

    result = _probe(client, "reranker", api_key=api_key, api_base=provider.api_base)

    assert result == {"success": True, "message": f"Validation successful (returned {hits} {noun})", "error": None}
    [seen] = provider.requests
    assert seen.path == "/v1/rerank"
    assert seen.authorization == f"Bearer {api_key}"
    assert str(seen.body["query"]).startswith("probe-")
    assert seen.body["documents"] == ["doc1", "doc2"]


def test_a_reranker_that_returns_nothing_fails_validation(
    client: TestClient, provider: FakeRetrievalProvider, api_key: str
) -> None:
    provider.rerank_results = []

    result = _probe(client, "reranker", api_key=api_key, api_base=provider.api_base)

    assert result == {"success": False, "message": "Validation failed: the provider returned no results", "error": None}


def test_an_embedding_without_values_fails_validation(client: TestClient, provider: FakeRetrievalProvider, api_key: str) -> None:
    provider.dimension = 0

    result = _probe(client, "embedding", api_key=api_key, api_base=provider.api_base)

    assert result == {"success": False, "message": "Validation failed: the provider returned no embedding", "error": None}


@pytest.mark.parametrize("kind", _KINDS)
@pytest.mark.parametrize(
    ("status", "cause"),
    [
        pytest.param(401, "the provider rejected the API key", id="invalid-key"),
        pytest.param(402, "the provider account has no quota or balance left", id="no-quota"),
        pytest.param(403, "the provider rejected the API key", id="forbidden-key"),
        pytest.param(404, "the provider does not know this model or endpoint", id="unknown-model"),
        pytest.param(429, "the provider rate-limited the request", id="rate-limited"),
    ],
)
def test_a_provider_refusal_is_named(
    client: TestClient, provider: FakeRetrievalProvider, api_key: str, kind: str, status: int, cause: str
) -> None:
    provider.status = status

    result = _probe(client, kind, api_key=api_key, api_base=provider.api_base)

    assert result["success"] is False
    assert result["message"] == f"Validation failed: {cause}"
    assert provider.requests[0].path == _PROVIDER_PATHS[kind]


@pytest.mark.parametrize("kind", _KINDS)
def test_a_bare_404_means_the_model_or_endpoint_is_unknown(
    client: TestClient, provider: FakeRetrievalProvider, api_key: str, kind: str
) -> None:
    # A wrong api_base path gets a generic "Not Found" from the server: nothing in it names a model.
    provider.status = 404
    provider.refusal = "Not Found"

    result = _probe(client, kind, api_key=api_key, api_base=provider.api_base)

    assert result["message"] == "Validation failed: the provider does not know this model or endpoint"


@pytest.mark.parametrize("kind", _KINDS)
@pytest.mark.parametrize(
    ("status", "words"),
    [
        pytest.param(400, "input is too long: at most 8192 tokens", id="bad-request"),
        pytest.param(422, "Unprocessable entity: unknown field `foo`", id="unprocessable"),
        pytest.param(500, "The upstream model server crashed", id="server-error"),
    ],
)
def test_a_refusal_with_no_cause_of_its_own_is_shown_in_the_providers_words(
    client: TestClient, provider: FakeRetrievalProvider, api_key: str, kind: str, status: int, words: str
) -> None:
    # The form shows `message` as is: a class name tells the user nothing, the provider's sentence tells what to change.
    provider.status = status
    provider.refusal = words

    result = _probe(client, kind, api_key=api_key, api_base=provider.api_base)

    assert result["message"] == f"Validation failed: {words}"


def test_a_gateway_error_page_is_shown_as_its_text(client: TestClient, provider: FakeRetrievalProvider, api_key: str) -> None:
    provider.status = 502
    provider.raw_answer = "<html><body><h1>502 Bad Gateway</h1></body></html>"

    result = _probe(client, "embedding", api_key=api_key, api_base=provider.api_base)

    assert result["message"] == "Validation failed: 502 Bad Gateway"


def test_a_refusal_with_no_words_names_the_status(client: TestClient, provider: FakeRetrievalProvider, api_key: str) -> None:
    provider.status = 500
    provider.raw_answer = ""

    result = _probe(client, "embedding", api_key=api_key, api_base=provider.api_base)

    assert result["message"] == "Validation failed: the provider answered HTTP 500"


def test_the_key_a_provider_repeats_in_its_words_is_not_shown(
    client: TestClient, provider: FakeRetrievalProvider, api_key: str
) -> None:
    provider.status = 400
    provider.refusal = f"invalid request for key {api_key}"

    result = _probe(client, "embedding", api_key=api_key, api_base=provider.api_base)

    assert api_key not in str(result)
    assert str(result["message"]).startswith("Validation failed: invalid request for key ")


@pytest.mark.parametrize("kind", _KINDS)
def test_a_model_no_provider_can_be_resolved_for_is_shown_by_the_text_of_the_failure(
    client: TestClient, api_key: str, kind: str
) -> None:
    result = _probe(client, kind, api_key=api_key, api_base=None, model="nomodel")

    assert result["message"] == (
        "Validation failed: Cannot resolve a provider for model 'nomodel': use a 'provider/model' id or set an api_base"
    )


def test_an_edited_key_is_checked_against_the_provider(client: TestClient, api_key: str) -> None:
    # A success for one key and endpoint says nothing about the key and endpoint the form was edited to afterwards.
    with fake_retrieval_provider() as accepting, fake_retrieval_provider() as refusing:
        refusing.status = 401

        accepted = _probe(client, "embedding", api_key=api_key, api_base=accepting.api_base)
        refused = _probe(client, "embedding", api_key=f"{api_key}-edited", api_base=refusing.api_base)

    assert accepted["success"] is True
    assert refused["message"] == "Validation failed: the provider rejected the API key"
    assert refusing.requests


@pytest.mark.parametrize("kind", _KINDS)
def test_a_repeated_probe_of_an_unchanged_configuration_reaches_the_provider_again(
    client: TestClient, provider: FakeRetrievalProvider, api_key: str, kind: str
) -> None:
    # Every probe carries a text no earlier call used: the provider could have gone away since the last probe, and a
    # fixed text answered from memory would still validate the form.
    _probe(client, kind, api_key=api_key, api_base=provider.api_base)
    _probe(client, kind, api_key=api_key, api_base=provider.api_base)

    assert len(provider.requests) == 2


@pytest.mark.parametrize("kind", _KINDS)
def test_an_unreachable_host_is_named(client: TestClient, api_key: str, kind: str) -> None:
    result = _probe(client, kind, api_key=api_key, api_base=unreachable_api_base())

    assert result["success"] is False
    assert result["message"] == "Validation failed: the provider endpoint could not be reached"


def test_the_key_a_provider_repeats_is_not_echoed_back(client: TestClient, provider: FakeRetrievalProvider, api_key: str) -> None:
    # The fake provider repeats the key in its error body; the transport puts that body into the exception text.
    provider.status = 401

    result = _probe(client, "embedding", api_key=api_key, api_base=provider.api_base)

    assert api_key not in str(result)
    assert "Incorrect API key provided: ***" in str(result["error"])


@pytest.mark.parametrize("kind", _KINDS)
def test_a_blank_key_does_not_shred_the_message(client: TestClient, provider: FakeRetrievalProvider, kind: str) -> None:
    # A key of one space matches every gap between words: there is nothing to hide, and hiding it would shred the text.
    result = _probe(client, kind, api_key=" ", api_base=provider.api_base)

    assert result["success"] is False
    assert "***" not in str(result)


@pytest.mark.parametrize("kind", _KINDS)
def test_a_missing_key_is_reported_without_calling_the_provider(
    client: TestClient, provider: FakeRetrievalProvider, kind: str
) -> None:
    result = _probe(client, kind, api_key="", api_base=provider.api_base)

    assert result == {"success": False, "message": "Validation failed: an API key is required", "error": None}
    assert provider.requests == []
