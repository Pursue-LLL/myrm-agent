"""Provider defaults WebSearcher applies when neither the config nor the query set a parameter.

Exa returns no page content unless asked and LiteLLM then asks for the full text of every result, so the default
is ``contents.highlights``. The wire-level cases go through the real LiteLLM request/response transformation with
only the HTTP layer faked, because what Exa actually receives is what the default has to be judged by.
"""

from __future__ import annotations

from collections.abc import Iterator

import httpx
import pytest
from litellm.llms.custom_httpx.http_handler import HTTPHandler

from myrm_agent_harness.toolkits.web_search.coalescing.search_coalescing import reset_search_coalescing_state_for_tests
from myrm_agent_harness.toolkits.web_search.core.common import SearchResult
from myrm_agent_harness.toolkits.web_search.providers.chain import ProviderQuotaTracker, search_provider_chain
from myrm_agent_harness.toolkits.web_search.providers.web_searcher import SearchServiceConfig, WebSearcher


@pytest.fixture(autouse=True)
def _clear_search_coalescing_state() -> Iterator[None]:
    reset_search_coalescing_state_for_tests()
    yield
    reset_search_coalescing_state_for_tests()


class _RecordingService:
    """Search client double that records the provider parameters of every call."""

    def __init__(self, results: list[SearchResult] | None = None) -> None:
        self.calls: list[dict[str, object]] = []
        self._results = results

    async def search(self, query: str, num_results: int = 5, **kwargs: object) -> list[SearchResult]:
        self.calls.append(kwargs)
        if self._results is not None:
            return self._results
        return [SearchResult(title="t", link=f"https://example.com/{query}", snippet="s")]


def _searcher(provider: str, extra_params: dict[str, object] | None = None) -> tuple[WebSearcher, _RecordingService]:
    searcher = WebSearcher(SearchServiceConfig(search_service=provider, api_key="key", extra_params=extra_params))
    service = _RecordingService()
    searcher._search_service = service
    return searcher, service


class TestExaDefault:
    @pytest.mark.asyncio
    async def test_exa_asks_for_highlights_unless_told_otherwise(self) -> None:
        searcher, service = _searcher("exa_ai")

        await searcher.search("exa default query")

        assert service.calls == [{"contents": {"highlights": True}}]

    @pytest.mark.asyncio
    async def test_config_extra_params_replace_the_default(self) -> None:
        searcher, service = _searcher("exa_ai", {"contents": {"text": {"maxCharacters": 2000}}})

        await searcher.search("exa configured query")

        assert service.calls == [{"contents": {"text": {"maxCharacters": 2000}}}]

    @pytest.mark.asyncio
    async def test_other_parameters_keep_the_default_next_to_them(self) -> None:
        searcher, service = _searcher("exa_ai", {"category": "news"})

        await searcher.search("exa category query", extra_params_override={"type": "neural"})

        assert service.calls == [{"category": "news", "type": "neural", "contents": {"highlights": True}}]

    @pytest.mark.asyncio
    async def test_the_default_is_not_shared_between_calls(self) -> None:
        searcher, service = _searcher("exa_ai")
        await searcher.search("first exa query")
        first_contents = service.calls[0]["contents"]
        assert isinstance(first_contents, dict)
        first_contents["text"] = True  # a consumer mutating what it received

        await searcher.search("second exa query")

        assert service.calls[1] == {"contents": {"highlights": True}}


class TestOtherProviders:
    @pytest.mark.asyncio
    async def test_a_provider_without_defaults_receives_nothing_extra(self) -> None:
        searcher, service = _searcher("tavily")

        await searcher.search("tavily query")

        assert service.calls == [{}]

    @pytest.mark.asyncio
    async def test_searxng_defaults_fill_every_unset_parameter(self) -> None:
        searcher, service = _searcher("searxng")

        await searcher.search("searxng default query")

        assert service.calls == [{"language": "auto", "categories": "general", "safesearch": "0"}]

    @pytest.mark.asyncio
    async def test_searxng_defaults_never_replace_what_the_caller_set(self) -> None:
        searcher, service = _searcher("searxng", {"language": "zh"})

        await searcher.search("searxng configured query", extra_params_override={"categories": "science"})

        assert service.calls == [{"language": "zh", "categories": "science", "safesearch": "0"}]


@pytest.mark.asyncio
async def test_each_chain_hop_gets_the_defaults_of_its_own_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    services = {"exa_ai": _RecordingService(results=[]), "tavily": _RecordingService()}

    async def fake_get_service(self: WebSearcher, bypass_gateway: bool = False) -> _RecordingService:
        return services[self.config.search_service]

    monkeypatch.setattr(WebSearcher, "_get_search_service", fake_get_service)
    hops = [SearchServiceConfig(search_service=slug, api_key="key") for slug in ("exa_ai", "tavily")]

    _, winner = await search_provider_chain(hops, "chain query", 5, quota_tracker=ProviderQuotaTracker())

    assert winner == "tavily"
    assert services["exa_ai"].calls == [{"contents": {"highlights": True}}]
    assert services["tavily"].calls == [{}]


class TestExaOnTheWire:
    @staticmethod
    def _fake_exa(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, object]]:
        """Fake only the HTTP POST of LiteLLM's client; return the JSON bodies that were sent."""
        sent: list[dict[str, object]] = []
        reply = {
            "results": [
                {"title": "Raft", "url": "https://a.example/raft", "highlights": ["first passage", "second passage"]},
                {"title": "Paxos", "url": "https://b.example/paxos", "text": "whole page text"},
                {"title": "Gossip", "url": "https://c.example/gossip", "highlights": []},
            ]
        }

        def fake_post(self: HTTPHandler, url: str, **kwargs: object) -> httpx.Response:
            body = kwargs.get("json")
            assert isinstance(body, dict)
            sent.append(body)
            return httpx.Response(200, json=reply, request=httpx.Request("POST", url))

        monkeypatch.setattr(HTTPHandler, "post", fake_post)
        return sent

    @pytest.mark.asyncio
    async def test_the_default_request_asks_exa_for_highlights_only(self, monkeypatch: pytest.MonkeyPatch) -> None:
        sent = self._fake_exa(monkeypatch)
        searcher = WebSearcher(SearchServiceConfig(search_service="exa_ai", api_key="key"))

        results = await searcher.search("wire default query", num_results=3)

        assert sent[0]["contents"] == {"highlights": True}
        assert [r.snippet for r in results] == ["first passage\n\nsecond passage", "whole page text", ""]
        assert [r.link for r in results] == [
            "https://a.example/raft",
            "https://b.example/paxos",
            "https://c.example/gossip",
        ]

    @pytest.mark.asyncio
    async def test_a_configured_contents_option_reaches_exa_unchanged(self, monkeypatch: pytest.MonkeyPatch) -> None:
        sent = self._fake_exa(monkeypatch)
        config = SearchServiceConfig(
            search_service="exa_ai", api_key="key", extra_params={"contents": {"text": {"maxCharacters": 2000}}}
        )

        await WebSearcher(config).search("wire configured query", num_results=3)

        assert sent[0]["contents"] == {"text": {"maxCharacters": 2000}}
