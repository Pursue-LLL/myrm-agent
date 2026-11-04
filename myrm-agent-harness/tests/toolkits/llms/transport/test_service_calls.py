"""Embedding and rerank calls: endpoint resolution, request bodies and answer parsing."""

from __future__ import annotations

from collections.abc import Callable, Iterator

import pytest

from myrm_agent_harness.toolkits.llms.transport import embeddings, rerank
from myrm_agent_harness.toolkits.llms.transport.http import PreparedRequest
from myrm_agent_harness.toolkits.llms.transport.profile import UnsupportedProviderError
from myrm_agent_harness.toolkits.llms.transport.service_routes import service_route

Answer = dict[str, object]
_ENTRY: list[dict[str, object]] = [{"index": 0, "relevance_score": 0.5}]
_ONE_RANKED: Answer = {"results": _ENTRY, "data": _ENTRY}  # Voyage answers under "data", the others under "results"


@pytest.fixture
def sent(monkeypatch: pytest.MonkeyPatch) -> Iterator[Callable[[Answer], list[PreparedRequest]]]:
    """Install a fake network for both modules; ``arm(answer)`` returns the list the requests land in."""
    requests: list[PreparedRequest] = []
    answer_box: list[Answer] = [{}]

    async def fake_send(request: PreparedRequest) -> Answer:
        requests.append(request)
        return answer_box[0]

    monkeypatch.setattr(embeddings, "asend_json", fake_send)
    monkeypatch.setattr(rerank, "asend_json", fake_send)

    def arm(answer: Answer) -> list[PreparedRequest]:
        answer_box[0] = answer
        return requests

    yield arm


class TestServiceRoute:
    def test_bare_openai_family_id_resolves_to_openai(self) -> None:
        route = service_route("text-embedding-3-small", api_key="k", api_base=None)
        assert (route.profile.id, route.model, route.base_url) == (
            "openai",
            "text-embedding-3-small",
            "https://api.openai.com/v1",
        )

    def test_provider_prefix_uses_the_provider_default_endpoint(self) -> None:
        route = service_route("jina_ai/jina-embeddings-v3", api_key="k", api_base=None)
        assert (route.profile.id, route.model, route.base_url) == (
            "jina_ai",
            "jina-embeddings-v3",
            "https://api.jina.ai/v1",
        )

    def test_unknown_prefix_with_base_keeps_the_whole_id(self) -> None:
        route = service_route("BAAI/bge-m3", api_key="k", api_base="https://api.siliconflow.cn/v1/")
        assert (route.profile.id, route.model, route.base_url) == (
            "openai_compatible",
            "BAAI/bge-m3",
            "https://api.siliconflow.cn/v1",
        )

    def test_openai_prefix_with_base_strips_only_the_provider(self) -> None:
        route = service_route("openai/BAAI/bge-m3", api_key="k", api_base="https://gw.example/v1")
        assert (route.profile.id, route.model, route.base_url) == ("openai", "BAAI/bge-m3", "https://gw.example/v1")

    @pytest.mark.parametrize("base", ["https://gw.example/v1/embeddings", "https://gw.example/v1/rerank"])
    def test_operation_url_is_reduced_to_the_root(self, base: str) -> None:
        assert service_route("m", api_key=None, api_base=base).base_url == "https://gw.example/v1"

    def test_unknown_id_without_base_is_rejected(self) -> None:
        with pytest.raises(UnsupportedProviderError):
            service_route("mystery-model", api_key="k", api_base=None)

    def test_no_environment_credential_is_read(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "from-env")
        monkeypatch.setenv("OPENAI_BASE_URL", "https://env.example/v1")
        assert service_route("text-embedding-3-small", api_key=None, api_base=None).api_key is None


class TestServiceEndpointFromEnvironment:
    """A service call that names no endpoint reaches its provider's own endpoint variable, else the default."""

    @pytest.mark.parametrize(
        ("model", "variable"),
        [
            ("text-embedding-3-small", "OPENAI_BASE_URL"),
            ("openai/text-embedding-3-small", "OPENAI_API_BASE"),
            ("azure/text-embedding-3-small", "AZURE_API_BASE"),
            ("azure/dall-e-3", "AZURE_OPENAI_ENDPOINT"),
            ("gemini/text-embedding-004", "GEMINI_API_BASE"),
            ("openrouter/openai/text-embedding-3-small", "OPENROUTER_API_BASE"),
            ("together_ai/BAAI/bge-large-en-v1.5", "TOGETHER_AI_API_BASE"),
            ("xai/grok-imagine-image", "XAI_API_BASE"),
            ("cohere/rerank-v3.5", "COHERE_API_BASE"),
            ("jina_ai/jina-reranker-v2-base-multilingual", "JINA_AI_API_BASE"),
            ("voyage/voyage-3", "VOYAGE_API_BASE"),
        ],
    )
    def test_the_providers_variable_replaces_its_default_endpoint(
        self, monkeypatch: pytest.MonkeyPatch, model: str, variable: str
    ) -> None:
        monkeypatch.setenv(variable, "https://env.example/v1/embeddings")
        assert service_route(model, api_key="k", api_base=None).base_url == "https://env.example/v1"

    def test_the_endpoint_of_the_call_wins_over_the_variable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENAI_BASE_URL", "https://env.example/v1")
        route = service_route("openai/text-embedding-3-small", api_key="k", api_base="https://gw.example/v1")
        assert route.base_url == "https://gw.example/v1"

    def test_a_variable_of_another_provider_is_not_used(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENAI_BASE_URL", "https://env.example/v1")
        monkeypatch.setenv("OPENAI_API_BASE", "https://env.example/v1")
        assert (
            service_route("jina_ai/jina-embeddings-v3", api_key="k", api_base=None).base_url == "https://api.jina.ai/v1"
        )

    def test_a_model_of_no_known_provider_still_needs_its_own_endpoint(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENAI_BASE_URL", "https://env.example/v1")
        with pytest.raises(UnsupportedProviderError):
            service_route("BAAI/bge-m3", api_key="k", api_base=None)

    async def test_azure_finds_its_resource_and_api_version_in_the_environment(
        self, monkeypatch: pytest.MonkeyPatch, sent: Callable[[Answer], list[PreparedRequest]]
    ) -> None:
        monkeypatch.setenv("AZURE_API_BASE", "https://res.openai.azure.com")
        monkeypatch.setenv("AZURE_API_VERSION", "2031-01-01")
        requests = sent({"data": [{"index": 0, "embedding": [1.0]}]})
        await embeddings.aembed("azure/text-embedding-3-small", ["a"], api_key="k")
        assert requests[0].url == "https://res.openai.azure.com/openai/deployments/text-embedding-3-small/embeddings"
        assert dict(requests[0].query) == {"api-version": "2031-01-01"}
        assert requests[0].headers["api-key"] == "k"


class TestEmbed:
    async def test_openai_shape_request_and_order(self, sent: Callable[[Answer], list[PreparedRequest]]) -> None:
        requests = sent(
            {"data": [{"index": 1, "embedding": [2.0]}, {"index": 0, "embedding": [1.0]}]},
        )
        vectors = await embeddings.aembed("text-embedding-3-small", ["a", "b"], api_key="sk")
        assert vectors == [[1.0], [2.0]]
        request = requests[0]
        assert request.url == "https://api.openai.com/v1/embeddings"
        assert request.headers["Authorization"] == "Bearer sk"
        assert request.body == {"model": "text-embedding-3-small", "input": ["a", "b"], "encoding_format": "float"}

    async def test_voyage_sends_no_encoding_format(self, sent: Callable[[Answer], list[PreparedRequest]]) -> None:
        requests = sent({"data": [{"index": 0, "embedding": [1.0]}]})
        await embeddings.aembed("voyage/voyage-3", ["a"], api_key="k")
        assert requests[0].url == "https://api.voyageai.com/v1/embeddings"
        assert requests[0].body is not None and "encoding_format" not in requests[0].body

    async def test_jina_sends_no_encoding_format(self, sent: Callable[[Answer], list[PreparedRequest]]) -> None:
        requests = sent({"data": [{"index": 0, "embedding": [1.0]}]})
        await embeddings.aembed("jina_ai/jina-embeddings-v3", ["a"], api_key="k")
        assert requests[0].url == "https://api.jina.ai/v1/embeddings"
        assert requests[0].body is not None and "encoding_format" not in requests[0].body

    async def test_custom_base_is_a_gateway_that_keeps_the_whole_model_id(
        self, sent: Callable[[Answer], list[PreparedRequest]]
    ) -> None:
        requests = sent({"data": [{"index": 0, "embedding": [1.0]}]})
        await embeddings.aembed("ollama/nomic-embed-text", ["a"], api_key="k", api_base="https://gw.example/v1")
        assert requests[0].url == "https://gw.example/v1/embeddings"
        assert requests[0].body == {"model": "ollama/nomic-embed-text", "input": ["a"], "encoding_format": "float"}

    async def test_gemini_uses_batch_embed_contents(self, sent: Callable[[Answer], list[PreparedRequest]]) -> None:
        requests = sent({"embeddings": [{"values": [1.0, 2.0]}, {"values": [3.0, 4.0]}]})
        vectors = await embeddings.aembed("gemini/text-embedding-004", ["a", "b"], api_key="k")
        assert vectors == [[1.0, 2.0], [3.0, 4.0]]
        request = requests[0]
        assert (
            request.url
            == "https://generativelanguage.googleapis.com/v1beta/models/text-embedding-004:batchEmbedContents"
        )
        assert request.headers == {"x-goog-api-key": "k"}
        assert request.body == {
            "requests": [
                {"model": "models/text-embedding-004", "content": {"parts": [{"text": "a"}]}},
                {"model": "models/text-embedding-004", "content": {"parts": [{"text": "b"}]}},
            ]
        }

    async def test_azure_addresses_the_deployment(self, sent: Callable[[Answer], list[PreparedRequest]]) -> None:
        requests = sent({"data": [{"index": 0, "embedding": [1.0]}]})
        await embeddings.aembed("azure/my-embed", ["a"], api_key="k", api_base="https://res.openai.azure.com")
        request = requests[0]
        assert request.url == "https://res.openai.azure.com/openai/deployments/my-embed/embeddings"
        assert request.headers["api-key"] == "k"
        assert "api-version" in request.query

    async def test_ollama_uses_the_openai_shape_under_v1(self, sent: Callable[[Answer], list[PreparedRequest]]) -> None:
        requests = sent({"data": [{"index": 0, "embedding": [1.0]}]})
        await embeddings.aembed("ollama/nomic-embed-text", ["a"], api_key="x")
        assert requests[0].url == "http://localhost:11434/v1/embeddings"

    async def test_cohere_native_shape(self, sent: Callable[[Answer], list[PreparedRequest]]) -> None:
        requests = sent({"embeddings": {"float": [[1.0, 2.0], [3.0, 4.0]]}})
        vectors = await embeddings.aembed("cohere/embed-english-v3.0", ["a", "b"], api_key="k")
        assert vectors == [[1.0, 2.0], [3.0, 4.0]]
        assert requests[0].url == "https://api.cohere.com/v2/embed"
        assert requests[0].body == {
            "model": "embed-english-v3.0",
            "texts": ["a", "b"],
            "input_type": "search_document",
            "embedding_types": ["float"],
        }

    async def test_wrong_vector_count_is_an_error(self, sent: Callable[[Answer], list[PreparedRequest]]) -> None:
        sent({"data": [{"index": 0, "embedding": [1.0]}]})
        with pytest.raises(ValueError, match="1 vectors for 2 inputs"):
            await embeddings.aembed("text-embedding-3-small", ["a", "b"], api_key="k")


class TestRerank:
    async def test_shared_shape(self, sent: Callable[[Answer], list[PreparedRequest]]) -> None:
        requests = sent({"results": [{"index": 1, "relevance_score": 0.9}, {"index": 0, "relevance_score": 0.1}]})
        ranked = await rerank.arerank("cohere/rerank-v3.5", "q", ["d0", "d1"], top_n=2, api_key="k")
        assert ranked == [(1, 0.9), (0, 0.1)]
        request = requests[0]
        assert request.url == "https://api.cohere.com/v2/rerank"
        assert request.headers["Authorization"] == "Bearer k"
        assert request.body == {"model": "rerank-v3.5", "query": "q", "documents": ["d0", "d1"], "top_n": 2}

    async def test_compatible_gateway_keeps_the_whole_model_id(
        self, sent: Callable[[Answer], list[PreparedRequest]]
    ) -> None:
        requests = sent({"results": [{"index": 0, "relevance_score": 0.5}]})
        await rerank.arerank(
            "BAAI/bge-reranker-v2-m3", "q", ["d"], top_n=1, api_key="k", api_base="https://api.siliconflow.cn/v1"
        )
        assert requests[0].url == "https://api.siliconflow.cn/v1/rerank"
        assert requests[0].body is not None and requests[0].body["model"] == "BAAI/bge-reranker-v2-m3"

    @pytest.mark.parametrize(
        ("model", "base", "url"),
        [
            ("cohere/rerank-v3.5", "https://gw", "https://gw/v2/rerank"),
            ("cohere/rerank-v3.5", "https://gw/", "https://gw/v2/rerank"),
            ("cohere/rerank-v3.5", "https://gw/cohere", "https://gw/cohere/v2/rerank"),
            ("cohere/rerank-v3.5", "https://gw/v1", "https://gw/v1/rerank"),
            ("cohere/rerank-v3.5", "https://gw/v2/rerank", "https://gw/v2/rerank"),
            ("jina_ai/jina-reranker-v2-base-multilingual", "https://gw", "https://gw/v1/rerank"),
            ("jina_ai/jina-reranker-v2-base-multilingual", "https://gw/jina", "https://gw/jina/v1/rerank"),
            ("jina_ai/jina-reranker-v2-base-multilingual", "https://gw/jina/v1", "https://gw/jina/v1/rerank"),
            ("voyage/rerank-2", "https://gw", "https://gw/v1/rerank"),
            ("voyage/rerank-2", "https://gw/v1/rerank", "https://gw/v1/rerank"),
            ("together_ai/Salesforce/Llama-Rank-V1", "https://gw/api", "https://gw/api/rerank"),
            ("BAAI/bge-reranker-v2-m3", "https://gw", "https://gw/rerank"),
        ],
    )
    async def test_a_custom_endpoint_is_completed_with_the_providers_version(
        self, sent: Callable[[Answer], list[PreparedRequest]], model: str, base: str, url: str
    ) -> None:
        requests = sent(_ONE_RANKED)
        await rerank.arerank(model, "q", ["d"], top_n=1, api_key="k", api_base=base)
        assert requests[0].url == url

    @pytest.mark.parametrize(
        ("model", "variable", "url"),
        [
            ("cohere/rerank-v3.5", "COHERE_API_BASE", "https://env.example/v2/rerank"),
            ("jina_ai/jina-reranker-v2-base-multilingual", "JINA_AI_API_BASE", "https://env.example/v1/rerank"),
            ("voyage/rerank-2", "VOYAGE_API_BASE", "https://env.example/v1/rerank"),
        ],
    )
    async def test_the_endpoint_variable_is_completed_the_same_way(
        self,
        monkeypatch: pytest.MonkeyPatch,
        sent: Callable[[Answer], list[PreparedRequest]],
        model: str,
        variable: str,
        url: str,
    ) -> None:
        monkeypatch.setenv(variable, "https://env.example")
        requests = sent(_ONE_RANKED)
        await rerank.arerank(model, "q", ["d"], top_n=1, api_key="k")
        assert requests[0].url == url

    async def test_voyage_uses_top_k_and_data(self, sent: Callable[[Answer], list[PreparedRequest]]) -> None:
        requests = sent({"data": [{"index": 0, "relevance_score": 0.7}]})
        ranked = await rerank.arerank("voyage/rerank-2", "q", ["d"], top_n=1, api_key="k")
        assert ranked == [(0, 0.7)]
        assert requests[0].body is not None
        assert requests[0].body["top_k"] == 1 and "top_n" not in requests[0].body

    async def test_out_of_range_index_is_an_error(self, sent: Callable[[Answer], list[PreparedRequest]]) -> None:
        sent({"results": [{"index": 5, "relevance_score": 0.5}]})
        with pytest.raises(ValueError, match="does not match"):
            await rerank.arerank("cohere/rerank-v3.5", "q", ["d"], top_n=1, api_key="k")

    async def test_provider_without_default_endpoint_needs_a_base(
        self, sent: Callable[[Answer], list[PreparedRequest]]
    ) -> None:
        sent({})
        with pytest.raises(UnsupportedProviderError):
            await rerank.arerank("azure/some", "q", ["d"], top_n=1, api_key="k")
