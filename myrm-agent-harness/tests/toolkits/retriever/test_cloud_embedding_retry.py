"""Cloud embedding retries what a second attempt can fix, waits as long as the provider asks, and fails fast otherwise."""

from __future__ import annotations

from collections.abc import Sequence

import httpx
import pytest
from tenacity import AsyncRetrying

from myrm_agent_harness.toolkits.llms.transport.errors import LLMHTTPError
from myrm_agent_harness.toolkits.retriever.embedding import cloud_embedding
from myrm_agent_harness.toolkits.retriever.embedding.cloud_embedding import CloudEmbedding, _is_transient


def _refusal(status: int, retry_after: str | None = None) -> LLMHTTPError:
    headers = {"Retry-After": retry_after} if retry_after else {}
    request = httpx.Request("POST", "https://provider.test/v1/embeddings")
    return LLMHTTPError("openai", status, "refused", httpx.Response(status, headers=headers, request=request))


class TestWhatIsTransient:
    @pytest.mark.parametrize("status", [408, 409, 429, 500, 502, 503, 504, 599])
    def test_a_timeout_conflict_rate_limit_or_server_fault_is_worth_another_attempt(self, status: int) -> None:
        assert _is_transient(_refusal(status)) is True

    @pytest.mark.parametrize("status", [400, 401, 403, 404, 413, 422])
    def test_a_refusal_the_provider_will_repeat_is_not(self, status: int) -> None:
        assert _is_transient(_refusal(status)) is False

    @pytest.mark.parametrize(
        "error",
        [httpx.ConnectError("refused"), httpx.ReadTimeout("slow"), TimeoutError(), ConnectionResetError(), OSError()],
        ids=["connect", "read-timeout", "timeout", "connection-reset", "os-error"],
    )
    def test_a_dropped_or_timed_out_connection_is_worth_another_attempt(self, error: BaseException) -> None:
        assert _is_transient(error) is True

    @pytest.mark.parametrize("error", [ValueError("malformed vector"), RuntimeError("bug"), KeyError("data")])
    def test_a_malformed_answer_or_a_bug_is_not(self, error: BaseException) -> None:
        assert _is_transient(error) is False


class _Provider:
    """``aembed`` stand-in that fails with ``failures`` in turn and then answers."""

    def __init__(self, failures: Sequence[BaseException]) -> None:
        self._failures = list(failures)
        self.calls = 0

    async def __call__(self, model: str, texts: Sequence[str], **_: object) -> list[list[float]]:
        self.calls += 1
        if self._failures:
            raise self._failures.pop(0)
        return [[0.5, 0.25] for _ in texts]


@pytest.fixture
def waits(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Seconds every retry pause asked for; the pauses themselves are skipped."""
    pauses: list[float] = []

    async def record(seconds: float) -> None:
        pauses.append(seconds)

    original = CloudEmbedding._retrying

    def recording(self: CloudEmbedding) -> AsyncRetrying:
        retrying = original(self)
        retrying.sleep = record
        return retrying

    monkeypatch.setattr(CloudEmbedding, "_retrying", recording)
    return pauses


def _service(monkeypatch: pytest.MonkeyPatch, provider: _Provider, *, wait: float = 0.0) -> CloudEmbedding:
    monkeypatch.setattr(cloud_embedding, "aembed", provider)
    return CloudEmbedding(model="text-embedding-3-small", api_key="k", retry_wait_min=wait, retry_wait_max=wait)


class TestRetry:
    async def test_a_gateway_hiccup_is_retried_until_the_provider_answers(
        self, monkeypatch: pytest.MonkeyPatch, waits: list[float]
    ) -> None:
        provider = _Provider([_refusal(503), _refusal(502)])

        vectors = await _service(monkeypatch, provider).embed_batch(["hello"])

        assert vectors == [[0.5, 0.25]]
        assert provider.calls == 3

    async def test_a_rate_limit_is_retried_too(self, monkeypatch: pytest.MonkeyPatch, waits: list[float]) -> None:
        provider = _Provider([_refusal(429)])

        assert await _service(monkeypatch, provider).embed_batch(["hello"]) == [[0.5, 0.25]]
        assert provider.calls == 2

    async def test_the_single_text_path_retries_the_same_way(
        self, monkeypatch: pytest.MonkeyPatch, waits: list[float]
    ) -> None:
        provider = _Provider([httpx.ConnectError("refused")])

        assert await _service(monkeypatch, provider).embed("hello") == [0.5, 0.25]
        assert provider.calls == 2

    async def test_a_refusal_that_will_repeat_fails_on_the_first_attempt(
        self, monkeypatch: pytest.MonkeyPatch, waits: list[float]
    ) -> None:
        provider = _Provider([_refusal(401)])

        with pytest.raises(LLMHTTPError) as raised:
            await _service(monkeypatch, provider).embed_batch(["hello"])

        assert raised.value.status_code == 401
        assert provider.calls == 1
        assert waits == []

    async def test_a_provider_that_stays_down_fails_after_the_configured_attempts(
        self, monkeypatch: pytest.MonkeyPatch, waits: list[float]
    ) -> None:
        provider = _Provider([_refusal(503)] * 10)

        with pytest.raises(LLMHTTPError) as raised:
            await _service(monkeypatch, provider).embed_batch(["hello"])

        assert raised.value.status_code == 503
        assert provider.calls == 3, "the first attempt plus two retries"
        assert len(waits) == 2

    async def test_a_malformed_answer_is_never_retried(
        self, monkeypatch: pytest.MonkeyPatch, waits: list[float]
    ) -> None:
        provider = _Provider([ValueError("Embedding provider returned a malformed vector")])

        with pytest.raises(ValueError, match="malformed vector"):
            await _service(monkeypatch, provider).embed_batch(["hello"])

        assert provider.calls == 1


class TestWaiting:
    async def test_the_provider_stated_boundary_is_waited_out(
        self, monkeypatch: pytest.MonkeyPatch, waits: list[float]
    ) -> None:
        provider = _Provider([_refusal(429, retry_after="7")])

        await _service(monkeypatch, provider).embed_batch(["hello"])

        assert waits == [7.0]

    async def test_a_boundary_shorter_than_the_backoff_never_shortens_it(
        self, monkeypatch: pytest.MonkeyPatch, waits: list[float]
    ) -> None:
        provider = _Provider([_refusal(429, retry_after="1")])

        await _service(monkeypatch, provider, wait=3.0).embed_batch(["hello"])

        assert waits == [3.0]

    @pytest.mark.parametrize(
        "retry_after", ["120", "soon", "0", "-5"], ids=["over-a-minute", "not-a-number", "zero", "negative"]
    )
    async def test_a_boundary_that_is_a_quota_or_unreadable_leaves_the_backoff_alone(
        self, monkeypatch: pytest.MonkeyPatch, waits: list[float], retry_after: str
    ) -> None:
        provider = _Provider([_refusal(429, retry_after=retry_after)])

        await _service(monkeypatch, provider, wait=2.0).embed_batch(["hello"])

        assert waits == [2.0]

    async def test_the_backoff_grows_between_attempts(
        self, monkeypatch: pytest.MonkeyPatch, waits: list[float]
    ) -> None:
        provider = _Provider([_refusal(503), _refusal(503)])
        monkeypatch.setattr(cloud_embedding, "aembed", provider)
        service = CloudEmbedding(model="text-embedding-3-small", api_key="k", retry_wait_min=1.0, retry_wait_max=4.0)

        await service.embed_batch(["hello"])

        assert waits == [1.0, 2.0]


class _Cache:
    """In-memory ``EmbeddingCacheProtocol`` that remembers what was asked of it."""

    def __init__(self, stored: dict[str, list[float]] | None = None) -> None:
        self.stored = dict(stored or {})
        self.batch_writes: list[tuple[list[str], list[list[float]]]] = []

    async def get(self, text: str) -> list[float] | None:
        return self.stored.get(text)

    async def put(self, text: str, embedding: list[float]) -> None:
        self.stored[text] = embedding

    async def get_batch(self, texts: list[str]) -> list[list[float] | None]:
        return [self.stored.get(text) for text in texts]

    async def put_batch(self, texts: list[str], embeddings: list[list[float]]) -> None:
        self.batch_writes.append((list(texts), [list(vector) for vector in embeddings]))
        self.stored.update(zip(texts, embeddings, strict=True))


def _cached_service(monkeypatch: pytest.MonkeyPatch, provider: _Provider, cache: _Cache) -> CloudEmbedding:
    monkeypatch.setattr(cloud_embedding, "aembed", provider)
    return CloudEmbedding(model="text-embedding-3-small", api_key="k", cache=cache, retry_wait_min=0, retry_wait_max=0)


class TestCache:
    """Only what the cache lacks is sent to the provider, every answer lands back in input order, and a retry still
    covers the call that fills the gaps."""

    async def test_a_batch_asks_the_provider_only_for_the_texts_the_cache_lacks(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        sent: list[Sequence[str]] = []

        async def provider(model: str, texts: Sequence[str], **_: object) -> list[list[float]]:
            sent.append(list(texts))
            return [[float(len(text))] for text in texts]

        cache = _Cache({"known": [9.0]})
        monkeypatch.setattr(cloud_embedding, "aembed", provider)
        service = CloudEmbedding(model="text-embedding-3-small", api_key="k", cache=cache)

        vectors = await service.embed_batch(["alpha", "known", "be"])

        assert sent == [["alpha", "be"]]
        assert vectors == [[5.0], [9.0], [2.0]], "each vector sits at the position of its text"
        assert cache.batch_writes == [(["alpha", "be"], [[5.0], [2.0]])]

    async def test_a_batch_the_cache_fully_holds_never_reaches_the_provider(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        provider = _Provider([])
        cache = _Cache({"a": [1.0], "b": [2.0]})

        vectors = await _cached_service(monkeypatch, provider, cache).embed_batch(["b", "a"])

        assert vectors == [[2.0], [1.0]]
        assert provider.calls == 0
        assert cache.batch_writes == []

    async def test_the_call_that_fills_the_gaps_is_retried_and_cached_once_it_answers(
        self, monkeypatch: pytest.MonkeyPatch, waits: list[float]
    ) -> None:
        provider = _Provider([_refusal(503)])
        cache = _Cache({"known": [9.0]})

        vectors = await _cached_service(monkeypatch, provider, cache).embed_batch(["known", "new"])

        assert vectors == [[9.0], [0.5, 0.25]]
        assert provider.calls == 2
        assert cache.batch_writes == [(["new"], [[0.5, 0.25]])]

    async def test_a_failed_call_leaves_the_cache_untouched(
        self, monkeypatch: pytest.MonkeyPatch, waits: list[float]
    ) -> None:
        provider = _Provider([_refusal(401)])
        cache = _Cache()

        with pytest.raises(LLMHTTPError):
            await _cached_service(monkeypatch, provider, cache).embed_batch(["new"])

        assert cache.stored == {}

    async def test_a_single_text_is_served_from_the_cache_or_fetched_and_remembered(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        provider = _Provider([])
        cache = _Cache({"known": [9.0]})
        service = _cached_service(monkeypatch, provider, cache)

        assert await service.embed("known") == [9.0]
        assert provider.calls == 0

        assert await service.embed("new") == [0.5, 0.25]
        assert provider.calls == 1
        assert cache.stored["new"] == [0.5, 0.25]
