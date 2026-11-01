"""REST search client: one class for every keyed search provider.

[INPUT]
- providers.search_adapters::ADAPTERS (POS: per-provider request and response shapes)
- infra.tls_compat::create_httpx_client (POS: TLS-compatible httpx client factory)
- web_search.core.common::SearchResult (POS: Unified search result dataclass)

[OUTPUT]
- RestSearch: async search client for perplexity, tavily, exa_ai, parallel_ai, google_pse, dataforseo, firecrawl,
  searxng, brave and serper
- SearchHTTPError: a non-2xx provider answer (status code and body text, for the failure classifier)

[POS]
Sends the request an adapter built and turns the answer into ``SearchResult`` rows. A provider failure surfaces as
an exception that carries ``status_code`` and the body text, so the search retry loop and the quota / rate-limit
classifier read it the same way for every provider; timeouts and dropped connections become the standard
``TimeoutError`` / ``ConnectionError`` the loop already treats as retryable. Only the credential passed in is
used: no provider key is read from the environment.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping

import httpx

from myrm_agent_harness.infra.tls_compat import create_httpx_client
from myrm_agent_harness.toolkits.web_search.core.common import SearchResult
from myrm_agent_harness.toolkits.web_search.core.exceptions import SearchConfigError
from myrm_agent_harness.toolkits.web_search.providers.search_adapters import ADAPTERS, SearchRequest

_BODY_LIMIT = 500


class SearchHTTPError(Exception):
    """A provider answered with a non-2xx status."""

    def __init__(self, provider: str, status_code: int, body: str) -> None:
        self.status_code = status_code
        self.body = body[:_BODY_LIMIT]
        super().__init__(f"{provider} search failed: HTTP {status_code}: {self.body}")


class RestSearch:
    """Async search client for one provider; ``search_provider`` is its slug (a key of ``ADAPTERS``)."""

    def __init__(
        self,
        search_provider: str,
        api_key: str | None = None,
        api_base: str | None = None,
        timeout_seconds: int | None = 20,
    ):
        if search_provider not in ADAPTERS:
            raise SearchConfigError(f"Unsupported search provider '{search_provider}'", config_key="search_service")
        self.search_provider = search_provider
        self.api_key = api_key
        self.api_base = api_base
        self.timeout_seconds = timeout_seconds or 20

    async def search(self, query: str, num_results: int = 5, **kwargs: object) -> list[SearchResult]:
        """Search ``query`` for up to ``num_results`` rows.

        ``kwargs`` are the unified parameters (``search_domain_filter``, ``country``, ``max_tokens_per_page``) and
        the provider's own options (Tavily ``topic`` / ``search_depth``, SearXNG ``categories`` / ``engines``,
        Firecrawl ``scrapeOptions``, Google PSE ``search_engine_id``, ...); the latter pass through unchanged.
        """
        adapter = ADAPTERS[self.search_provider]
        request = adapter.build(query, num_results, kwargs, self.api_key, self.api_base)
        payload = await asyncio.wait_for(self._send(request), timeout=self.timeout_seconds)
        return [SearchResult.from_dict(row) for row in adapter.parse(payload, request)]

    async def _send(self, request: SearchRequest) -> Mapping[str, object]:
        provider = self.search_provider
        try:
            async with create_httpx_client(timeout=float(self.timeout_seconds), follow_redirects=True) as client:
                response = await client.request(
                    request.method,
                    request.url,
                    headers=request.headers,
                    params=request.params or None,
                    content=json.dumps(request.json_body, ensure_ascii=False).encode()
                    if request.json_body is not None
                    else None,
                )
        except httpx.TimeoutException as exc:
            raise TimeoutError(f"{provider} search request timed out") from exc
        except httpx.TransportError as exc:
            raise ConnectionError(f"{provider} search connection failed: {type(exc).__name__}: {exc}") from exc
        if not response.is_success:
            raise SearchHTTPError(provider, response.status_code, response.text)
        try:
            payload = response.json()
        except ValueError as exc:
            raise ValueError(f"{provider} search answered with a non-JSON body: {response.text[:200]!r}") from exc
        if not isinstance(payload, dict):
            raise ValueError(f"{provider} search answered with an unexpected JSON payload")
        return payload
