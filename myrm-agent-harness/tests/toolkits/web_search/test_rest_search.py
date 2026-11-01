"""REST search providers: request shapes, answer parsing and failure mapping, with only the HTTP round trip faked."""

from __future__ import annotations

import base64
import json
from collections.abc import Callable
from dataclasses import dataclass

import httpx
import pytest

from myrm_agent_harness.toolkits.web_search.core.error_handling import (
    is_persistent_quota_depleted_error,
    is_quota_or_rate_limit_error,
    is_retryable_search_error,
)
from myrm_agent_harness.toolkits.web_search.core.exceptions import SearchConfigError
from myrm_agent_harness.toolkits.web_search.providers import rest_search
from myrm_agent_harness.toolkits.web_search.providers.rest_search import RestSearch, SearchHTTPError


@dataclass
class _Sent:
    method: str
    url: str
    headers: dict[str, str]
    params: dict[str, object]
    body: object


@pytest.fixture
def network(monkeypatch: pytest.MonkeyPatch) -> Callable[[object, int], list[_Sent]]:
    """``arm(reply, status)`` fakes the next answer and returns the list the sent requests land in."""
    sent: list[_Sent] = []
    box: list[tuple[object, int]] = [({}, 200)]

    async def fake_request(self: httpx.AsyncClient, method: str, url: str, **kwargs: object) -> httpx.Response:
        content = kwargs.get("content")
        headers = kwargs.get("headers")
        params = kwargs.get("params")
        sent.append(
            _Sent(
                method=method,
                url=url,
                headers=dict(headers) if isinstance(headers, dict) else {},
                params=dict(params) if isinstance(params, dict) else {},
                body=json.loads(content) if isinstance(content, bytes) else None,
            )
        )
        reply, status = box[0]
        return httpx.Response(status, json=reply, request=httpx.Request(method, url))

    monkeypatch.setattr(httpx.AsyncClient, "request", fake_request)

    def arm(reply: object, status: int = 200) -> list[_Sent]:
        box[0] = (reply, status)
        return sent

    return arm


Arm = Callable[[object, int], list[_Sent]]


async def _search(provider: str, key: str | None = "key", base: str | None = None, **kwargs: object):
    return await RestSearch(provider, api_key=key, api_base=base).search("q text", 7, **kwargs)


class TestTavily:
    async def test_request_and_rows(self, network: Arm) -> None:
        sent = network({"results": [{"title": "T", "url": "https://a.example", "content": "C"}]})
        rows = await _search("tavily", search_domain_filter=["a.com"], country="US", topic="news")
        request = sent[0]
        assert (request.method, request.url) == ("POST", "https://api.tavily.com/search")
        assert request.headers["Authorization"] == "Bearer key"
        assert request.body == {
            "query": "q text",
            "max_results": 7,
            "include_domains": ["a.com"],
            "country": "us",
            "topic": "news",
        }
        assert [(r.title, r.link, r.snippet) for r in rows] == [("T", "https://a.example", "C")]

    async def test_gateway_base_gets_the_operation_path(self, network: Arm) -> None:
        sent = network({"results": []})
        await _search("tavily", base="https://gw.example/tavily")
        assert sent[0].url == "https://gw.example/tavily/search"

    async def test_extras_never_override_mapped_fields(self, network: Arm) -> None:
        sent = network({"results": []})
        await _search("tavily", search_domain_filter=["a.com"], include_domains=["evil.com"], max_results=99)
        assert sent[0].body == {"query": "q text", "max_results": 7, "include_domains": ["a.com"]}


class TestPerplexity:
    async def test_request_carries_only_the_unified_parameters(self, network: Arm) -> None:
        sent = network({"results": [{"title": "T", "url": "u", "snippet": "S", "date": "2025-01-02"}]})
        rows = await _search("perplexity", country="US", topic="ignored")
        assert sent[0].url == "https://api.perplexity.ai/search"
        assert sent[0].body == {"query": "q text", "max_results": 7, "country": "US"}
        assert rows[0].date == "2025-01-02"


class TestExa:
    async def test_defaults_ask_for_text_and_snippet_falls_back_to_highlights(self, network: Arm) -> None:
        sent = network(
            {
                "results": [
                    {"title": "A", "url": "u1", "highlights": ["x", "y"], "publishedDate": "2025-02-03"},
                    {"title": "B", "url": "u2", "text": "whole"},
                ]
            }
        )
        rows = await _search("exa_ai", country="US", search_domain_filter=["a.com"])
        assert sent[0].headers["x-api-key"] == "key"
        assert sent[0].body == {
            "query": "q text",
            "numResults": 7,
            "includeDomains": ["a.com"],
            "userLocation": "US",
            "contents": {"text": True},
        }
        assert [r.snippet for r in rows] == ["x\n\ny", "whole"]
        assert rows[0].date == "2025-02-03"


class TestParallel:
    async def test_advanced_settings_and_excerpts(self, network: Arm) -> None:
        sent = network({"results": [{"title": "T", "url": "u", "excerpts": ["a", "b"], "publish_date": "2025-01-01"}]})
        rows = await _search(
            "parallel_ai", base="https://api.parallel.ai/v1", search_domain_filter=["a.com"], processor="pro"
        )
        assert sent[0].url == "https://api.parallel.ai/v1/search"
        assert sent[0].body == {
            "search_queries": ["q text"],
            "objective": "q text",
            "mode": "advanced",
            "advanced_settings": {"max_results": 7, "source_policy": {"include_domains": ["a.com"]}},
        }
        assert rows[0].snippet == "a ... b"


class TestGooglePse:
    async def test_engine_id_travels_as_cx_and_is_not_repeated(self, network: Arm) -> None:
        sent = network({"items": [{"title": "T", "link": "https://a.example", "snippet": "S"}]})
        rows = await _search("google_pse", search_engine_id="CX1", search_domain_filter=["a.com"], country="de")
        request = sent[0]
        assert request.method == "GET"
        assert request.params == {
            "q": "q text",
            "cx": "CX1",
            "key": "key",
            "num": 7,
            "siteSearch": "a.com",
            "siteSearchFilter": "i",
            "gl": "DE",
        }
        assert rows[0].link == "https://a.example"

    async def test_missing_engine_id_is_a_config_error(self, network: Arm) -> None:
        network({})
        with pytest.raises(SearchConfigError, match="search engine id"):
            await _search("google_pse")


class TestDataForSeo:
    async def test_basic_auth_and_defaults(self, network: Arm) -> None:
        sent = network(
            {
                "tasks": [
                    {
                        "status_code": 20000,
                        "result": [
                            {
                                "items": [
                                    {"type": "organic", "title": "T", "url": "u", "description": "D"},
                                    {"type": "paid", "title": "ad", "url": "x", "description": "x"},
                                ]
                            }
                        ],
                    }
                ]
            }
        )
        rows = await _search("dataforseo", key="login:pass")
        expected = base64.b64encode(b"login:pass").decode()
        assert sent[0].headers["Authorization"] == f"Basic {expected}"
        assert sent[0].body == [{"keyword": "q text", "depth": 7, "language_code": "en", "location_code": 2250}]
        assert [(r.title, r.snippet) for r in rows] == [("T", "D")]

    async def test_a_caller_language_name_replaces_the_language_code_default(self, network: Arm) -> None:
        sent = network({"tasks": []})
        await _search("dataforseo", key="login:pass", language_name="German")
        task = sent[0].body[0]  # type: ignore[index]
        assert "language_code" not in task and task["language_name"] == "German"

    async def test_key_without_login_password_is_a_config_error(self, network: Arm) -> None:
        network({})
        with pytest.raises(SearchConfigError, match="login:password"):
            await _search("dataforseo", key="just-a-token")


class TestFirecrawl:
    async def test_markdown_scrape_default_and_both_sections(self, network: Arm) -> None:
        sent = network(
            {
                "data": {
                    "web": [{"title": "W", "url": "u1", "markdown": "# md", "description": "d"}],
                    "news": [{"title": "N", "url": "u2", "snippet": "s", "date": "2025-03-01"}],
                }
            }
        )
        rows = await _search("firecrawl", country="US")
        assert sent[0].url == "https://api.firecrawl.dev/v2/search"
        assert sent[0].body == {
            "query": "q text",
            "limit": 7,
            "country": "US",
            "scrapeOptions": {"formats": ["markdown"], "onlyMainContent": True},
        }
        assert [(r.snippet, r.date) for r in rows] == [("# md", None), ("s", "2025-03-01")]


class TestSearxng:
    async def test_get_with_json_format_and_country_language(self, network: Arm) -> None:
        sent = network({"results": [{"title": "T", "url": "u", "content": "C", "publishedDate": "2025-04-05"}]})
        rows = await _search("searxng", key=None, base="http://sx.local:8080", country="jp", categories="general")
        request = sent[0]
        assert (request.method, request.url) == ("GET", "http://sx.local:8080/search")
        assert request.params == {"q": "q text", "format": "json", "language": "ja", "categories": "general"}
        assert "Authorization" not in request.headers
        assert (rows[0].snippet, rows[0].date) == ("C", "2025-04-05")

    async def test_a_base_url_is_required(self, network: Arm) -> None:
        network({})
        with pytest.raises(SearchConfigError, match="api_base"):
            await _search("searxng", key=None)


class TestBrave:
    async def test_token_header_domain_query_and_section_cap(self, network: Arm) -> None:
        sent = network(
            {
                "web": {
                    "results": [{"title": "W", "url": "u1", "description": "d1", "page_age": "2025-05-06T00:00:00"}]
                },
                "news": {"results": [{"title": "N", "url": "u2", "description": "d2", "age": "2 days ago"}]},
            }
        )
        rows = await _search("brave", search_domain_filter=["a.com", "b.org"])
        request = sent[0]
        assert request.headers["X-Subscription-Token"] == "key"
        assert request.params["q"] == "(q text) AND (site:a.com OR site:b.org)"
        assert request.params["count"] == 7
        assert [(r.link, r.date) for r in rows] == [("u1", "2025-05-06"), ("u2", None)]

    async def test_result_filter_limits_the_sections_read(self, network: Arm) -> None:
        network(
            {
                "web": {"results": [{"title": "W", "url": "u1", "description": "d"}]},
                "news": {"results": [{"title": "N", "url": "u2", "description": "d"}]},
            }
        )
        rows = await _search("brave", result_filter="news")
        assert [r.link for r in rows] == ["u2"]


class TestSerper:
    async def test_domain_clause_and_organic_rows(self, network: Arm) -> None:
        sent = network(
            {"organic": [{"title": "T", "link": "https://a.example", "snippet": "S", "date": "Jan 1, 2025"}]}
        )
        rows = await _search("serper", search_domain_filter=["a.com"], country="US")
        assert sent[0].headers["X-API-KEY"] == "key"
        assert sent[0].body == {"q": "(q text) (site:a.com)", "num": 7, "gl": "us"}
        assert (rows[0].link, rows[0].date) == ("https://a.example", "Jan 1, 2025")


class TestCredentials:
    @pytest.mark.parametrize(
        "provider", ["tavily", "perplexity", "exa_ai", "serper", "brave", "firecrawl", "parallel_ai"]
    )
    async def test_a_keyed_provider_without_a_key_is_a_config_error(self, network: Arm, provider: str) -> None:
        network({})
        with pytest.raises(SearchConfigError, match="API key"):
            await _search(provider, key=None)

    async def test_no_environment_key_is_read(self, network: Arm, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TAVILY_API_KEY", "from-env")
        network({})
        with pytest.raises(SearchConfigError):
            await _search("tavily", key=None)


class TestFailures:
    async def test_quota_answer_is_classified_as_a_quota_failure(self, network: Arm) -> None:
        network({"detail": "Request exceeds your plan's set usage limit"}, 429)
        with pytest.raises(SearchHTTPError) as caught:
            await _search("tavily")
        assert caught.value.status_code == 429
        assert is_quota_or_rate_limit_error(caught.value)
        assert not is_retryable_search_error(caught.value)

    async def test_payment_required_is_persistent_quota_depletion(self, network: Arm) -> None:
        network({"error": "insufficient credits"}, 402)
        with pytest.raises(SearchHTTPError) as caught:
            await _search("serper")
        assert is_persistent_quota_depleted_error(caught.value)

    async def test_server_error_is_retryable_and_bad_request_is_not(self, network: Arm) -> None:
        network({"error": "boom"}, 503)
        with pytest.raises(SearchHTTPError) as server_error:
            await _search("serper")
        assert is_retryable_search_error(server_error.value)
        network({"error": "bad"}, 400)
        with pytest.raises(SearchHTTPError) as bad_request:
            await _search("serper")
        assert not is_retryable_search_error(bad_request.value)

    async def test_timeout_and_dropped_connection_become_standard_retryable_errors(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def slow(self: httpx.AsyncClient, method: str, url: str, **kwargs: object) -> httpx.Response:
            raise httpx.ReadTimeout("slow")

        monkeypatch.setattr(httpx.AsyncClient, "request", slow)
        with pytest.raises(TimeoutError) as timed_out:
            await _search("tavily")
        assert is_retryable_search_error(timed_out.value)

        async def refused(self: httpx.AsyncClient, method: str, url: str, **kwargs: object) -> httpx.Response:
            raise httpx.ConnectError("refused")

        monkeypatch.setattr(httpx.AsyncClient, "request", refused)
        with pytest.raises(ConnectionError) as dropped:
            await _search("tavily")
        assert is_retryable_search_error(dropped.value)

    async def test_a_redirect_is_reported_and_never_followed_with_the_credential(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        requested: list[str] = []

        def answer(request: httpx.Request) -> httpx.Response:
            requested.append(str(request.url))
            return httpx.Response(302, headers={"Location": "https://elsewhere.test/collect"}, request=request)

        def client_with_fake_network(**kwargs: object) -> httpx.AsyncClient:
            return httpx.AsyncClient(transport=httpx.MockTransport(answer), **kwargs)

        monkeypatch.setattr(rest_search, "create_httpx_client", client_with_fake_network)
        with pytest.raises(SearchHTTPError) as caught:
            await _search("serper")
        assert caught.value.status_code == 302
        assert requested == ["https://google.serper.dev/search"]

    async def test_non_json_answer_is_an_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        async def html(self: httpx.AsyncClient, method: str, url: str, **kwargs: object) -> httpx.Response:
            return httpx.Response(200, text="<html>", request=httpx.Request(method, url))

        monkeypatch.setattr(httpx.AsyncClient, "request", html)
        with pytest.raises(ValueError, match="non-JSON"):
            await _search("tavily")
