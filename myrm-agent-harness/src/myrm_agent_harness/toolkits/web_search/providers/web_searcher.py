"""WebSearcher — Multi-provider web search orchestrator.

Manages search provider configuration, query execution with retry,
result caching, single-flight coalescing, and conversion to LangChain Documents.

[INPUT]
core.config.gateway::ToolGatewayConfig (POS: Tool Gateway configuration, routes third-party tool requests through one gateway)
web_search.core.common::SearchResult (POS: Unified search result dataclass)
web_search.core.error_handling::build_search_error_context, is_retryable_search_error (POS: Search error classification)
web_search.core.exceptions::AllQueriesFailedError, ErrorContext, SearchAPIError (POS: Search exception types)
web_search.coalescing.search_coalescing::await_coalesced_search, bucket_search_limit, build_search_cache_key (POS: Search cache coalescing)
web_search.processing._explicit_params::resolve_site_operators, resolve_time_range (POS: Explicit constraint mapper; maps the query's site: operators and the time_range onto the serving provider's own parameters)
web_search.processing.search_results_processor::search_results_to_documents (POS: Search-result to Document converter)
web_search.providers.search_service_factory::SearchService, build_search_service, credential_scope_digest (POS: Provider client factory)
web_search.providers.chain::search_provider_chain (POS: Priority-ordered provider failover with quota tracking) [lazy]

[OUTPUT]
WebSearcher: Configurable multi-provider web search with LRU cache, single-flight coalescing, limit bucketing, retry, and Document output; an all-empty search names the time_range as a possible cause only when a provider this config can reach maps the requested time_range
SearchServiceConfig: Provider configuration model; provider_names lists the providers a request through it can reach (chain hops in priority order, else its own service)
SearchServiceType: str alias naming a search provider slug (the provider catalog is owned by the host application)

[POS]
Web search orchestrator. Provides a unified interface for querying multiple search
providers (Perplexity, Tavily, Exa, etc.) with caching, coalescing, retry, and error handling.
Each searcher serves one provider and translates the agent's explicit constraints into that provider's own
parameters, so a chain failover hands every hop the same query text, operators included, and never one provider's
parameters to another. Every result it returns names that provider.

"""

import asyncio
import json
import logging

from langchain_core.documents import Document
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from myrm_agent_harness.core.config.gateway import ToolGatewayConfig
from myrm_agent_harness.toolkits.web_search.coalescing.search_coalescing import (
    await_coalesced_search,
    bucket_search_limit,
    build_search_cache_key,
)
from myrm_agent_harness.toolkits.web_search.core.common import SearchResult
from myrm_agent_harness.toolkits.web_search.core.error_handling import (
    build_search_error_context,
    is_retryable_search_error,
)
from myrm_agent_harness.toolkits.web_search.core.exceptions import (
    AllQueriesFailedError,
    ErrorContext,
    SearchAPIError,
)
from myrm_agent_harness.toolkits.web_search.processing._explicit_params import (
    resolve_site_operators,
    resolve_time_range,
)
from myrm_agent_harness.toolkits.web_search.processing.search_results_processor import (
    search_results_to_documents,
)
from myrm_agent_harness.toolkits.web_search.providers.search_service_factory import (
    SearchService,
    build_search_service,
    credential_scope_digest,
)

SearchServiceType = str

# Configure logging
logger = logging.getLogger(__name__)


class SearchServiceConfig(BaseModel):
    """Search service configuration model (supports runtime updates)"""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    search_service: SearchServiceType = Field(..., description="Search service type (provider slug)")
    api_key: str | None = Field(default=None, description="API key (dynamically passed, supports multi-user)")
    api_base: str | None = Field(default=None, description="API base URL (for self-hosted services like SearxNG)")
    timeout_seconds: int | None = Field(default=20, description="Single search timeout (seconds)")
    extra_params: dict[str, object] | None = Field(
        default=None,
        description="Provider-specific parameters passed through to the search provider (categories, engines, language, etc.)",
    )
    search_max_retries: int = Field(
        default=2,
        ge=0,
        le=8,
        description="Number of retries after the first failed search attempt",
    )
    retry_backoff_base_seconds: float = Field(default=0.5, ge=0.0, le=60.0)
    retry_backoff_max_seconds: float = Field(default=8.0, ge=0.0, le=120.0)
    total_timeout_seconds: int | None = Field(
        default=None,
        description="Max wall-clock seconds for search() including retries; None derives from timeout and retry settings",
    )
    provider_chain: list["SearchServiceConfig"] | None = Field(
        default=None,
        description="Priority-ordered provider configs (priority 1 first). When set, search tries each hop on failure.",
    )
    gateway_config: ToolGatewayConfig | None = Field(
        default=None,
        description="Optional gateway configuration for routing traffic through the Unified Tool Gateway",
    )

    @property
    def provider_names(self) -> list[str]:
        """The providers a request through this config can reach: the chain hops in priority order, else its own."""
        return [hop.search_service for hop in self.provider_chain or [self]]


SearchServiceConfig.model_rebuild()


def _provider_default_params(provider: str) -> dict[str, object]:
    """Parameters a provider needs when neither the config nor the query set them; callers always win.

    A fresh dict per call: the search client and the retry loop receive these values and must not share state.
    """
    if provider == "searxng":
        return {"language": "auto", "categories": "general", "safesearch": "0"}
    if provider == "exa_ai":
        # Exa returns no page content unless asked, and the client's own default then asks for the full text of every result.
        # Highlights are the passages Exa picked for the query, which is what a search call should hand the
        # agent; reading a whole page is web_fetch's job.
        return {"contents": {"highlights": True}}
    return {}


class WebSearcher:
    """Web search core implementation class, only responsible for basic search functionality"""

    def __init__(self, config: SearchServiceConfig):
        """Initialize search tool

        Args:
            config: Search service configuration
        """
        self.config = config
        self._search_service: SearchService | None = None

    async def _get_search_service(self, bypass_gateway: bool = False) -> SearchService:
        """Return the search client, caching the one that follows the configured routing.

        Args:
            bypass_gateway: Connect to the provider directly; such a client is never cached because
                the cached one may be routed through the gateway.
        """
        if self._search_service is not None and not bypass_gateway:
            return self._search_service

        service = build_search_service(self.config, bypass_gateway=bypass_gateway)
        if not bypass_gateway:
            self._search_service = service
        return service

    def _compute_search_total_timeout_seconds(self) -> float:
        if self.config.total_timeout_seconds is not None:
            return float(self.config.total_timeout_seconds)
        per_attempt = float(self.config.timeout_seconds or 20)
        attempts = self.config.search_max_retries + 1
        backoff_sum = 0.0
        for i in range(self.config.search_max_retries):
            backoff_sum += min(
                self.config.retry_backoff_base_seconds * (2**i),
                self.config.retry_backoff_max_seconds,
            )
        return per_attempt * attempts + backoff_sum + 1.0

    async def search(
        self,
        query: str,
        num_results: int = 5,
        time_range: str | None = None,
    ) -> list[SearchResult]:
        """Search using configured search engine

        Args:
            query: Search query. Its ``site:`` operators are mapped onto the domain filters of the provider that
                   serves the request (each chain hop maps them for itself) and win over config.extra_params; a
                   provider this toolkit maps no domain filter for receives the query as written.
            num_results: Number of results to return
            time_range: Time window the agent explicitly asked for. It is mapped onto the parameters of the
                        provider that serves the request — each chain hop maps it for itself — and wins over
                        config.extra_params.

        Returns:
            List of search results
        """
        if self.config.provider_chain:
            from myrm_agent_harness.toolkits.web_search.providers.chain import (
                search_provider_chain,
            )

            results, _ = await search_provider_chain(
                self.config.provider_chain,
                query,
                num_results,
                time_range=time_range,
            )
            return results

        extra_params: dict[str, object] = dict(self.config.extra_params) if self.config.extra_params else {}
        query, site_params = resolve_site_operators(query, self.config.search_service)
        extra_params.update(site_params)
        if time_range:
            resolution = resolve_time_range(time_range, self.config.search_service)
            extra_params.update(resolution.params)
            if resolution.caveat:
                logger.info(
                    "Search time filter caveat (provider=%s): %s", self.config.search_service, resolution.caveat
                )

        for key, value in _provider_default_params(self.config.search_service).items():
            extra_params.setdefault(key, value)

        extra_suffix = json.dumps(extra_params, sort_keys=True, default=str) if extra_params else ""
        bucketed_limit = bucket_search_limit(num_results)
        cache_key = build_search_cache_key(
            self.config.search_service,
            query,
            bucketed_limit,
            extra_suffix,
            credential_scope_digest(self.config),
        )

        async def fetch() -> list[SearchResult]:
            results = await self._search_provider_with_retry(query, bucketed_limit, extra_params)
            # Stamped before the results enter the cache, whose key names the provider: a cached result keeps
            # naming the provider that served it.
            for result in results:
                result.provider = self.config.search_service
            return results

        return await await_coalesced_search(
            cache_key,
            bucketed_limit,
            num_results,
            fetch,
            log_label=query,
        )

    async def _search_provider_with_retry(
        self,
        query: str,
        num_results: int,
        extra_params: dict[str, object],
    ) -> list[SearchResult]:
        provider = self.config.search_service
        max_attempts = self.config.search_max_retries + 1
        bypass_gateway = False

        for attempt in range(max_attempts):
            try:
                search_service = await self._get_search_service(bypass_gateway=bypass_gateway)
                if extra_params:
                    results = await search_service.search(query, num_results, **extra_params)
                else:
                    results = await search_service.search(query, num_results)
            except Exception as exc:
                if (
                    not bypass_gateway
                    and self.config.gateway_config
                    and self.config.gateway_config.use_gateway
                    and self.config.api_key
                ):
                    error_msg = self._extract_key_error(exc).lower()
                    if (
                        "502" in error_msg
                        or "503" in error_msg
                        or "504" in error_msg
                        or "402" in error_msg
                        or "insufficient" in error_msg
                        or "timeout" in error_msg
                    ):
                        logger.warning(
                            "Gateway search failed (%s), falling back to direct provider API (BYOK)",
                            error_msg,
                        )
                        bypass_gateway = True
                        continue

                if not is_retryable_search_error(exc) or attempt >= max_attempts - 1:
                    ctx = build_search_error_context(
                        exc,
                        query=query,
                        provider=provider,
                        attempt_index=attempt,
                    )
                    raise SearchAPIError(
                        f"Search request failed: {self._extract_key_error(exc)}",
                        context=ctx,
                    ) from exc
                delay = min(
                    self.config.retry_backoff_base_seconds * (2**attempt),
                    self.config.retry_backoff_max_seconds,
                )
                await asyncio.sleep(delay)
                continue

            return results

        msg = f"Search request failed after {max_attempts} attempts"
        raise SearchAPIError(
            msg,
            context=build_search_error_context(
                RuntimeError(msg),
                query=query,
                provider=provider,
                attempt_index=max(0, max_attempts - 1),
            ),
        )

    async def search_and_process(
        self,
        query: str,
        num_results: int,
        time_range: str | None = None,
    ) -> tuple[str, list[Document], Exception | None]:
        """Execute single query and process results for compound search

        Args:
            query: Query string
            num_results: Number of results to return
            time_range: Time window the agent explicitly asked for

        Returns:
            Query, documents list and possible exception
        """
        total_timeout = self._compute_search_total_timeout_seconds()
        try:
            logger.debug("Searching query: %s", query)
            search_results = await asyncio.wait_for(
                self.search(
                    query=query,
                    num_results=num_results,
                    time_range=time_range,
                ),
                timeout=total_timeout,
            )

            documents = search_results_to_documents(search_results)
            return query, documents, None
        except TimeoutError:
            ctx = ErrorContext(
                query=query,
                retryable=True,
                error_code="TimeoutError",
                metadata={
                    "provider": self.config.search_service,
                    "phase": "search_and_process",
                    "total_timeout_seconds": str(int(total_timeout)),
                },
            )
            err = SearchAPIError("Search exceeded total time budget (including retries)", context=ctx)
            logger.warning(f"Search '{query}' failed: {err.message}")
            return query, [], err
        except Exception as e:
            error_msg = self._extract_key_error(e)
            logger.warning(f"Search '{query}' failed: {error_msg}")
            return query, [], e

    def _extract_key_error(self, e: Exception) -> str:
        """Extract key error information from exception, filtering out redundant stack trace information

        Args:
            e: Exception object

        Returns:
            Concise error message string
        """
        error_str = str(e)
        error_lower = error_str.lower()

        # Semantic checks first: content-based matching must precede class-name matching, because
        # a provider failure reaches this point wrapped in generic connection or timeout classes.
        if "exceeds" in error_lower and ("usage limit" in error_lower or "plan" in error_lower):
            return "Search service quota exceeded — upgrade your plan or use a different API key"
        if "invalid api key" in error_lower or "invalid_api_key" in error_lower:
            return "Search service authentication failed — invalid API key"
        if "rate limit" in error_lower or "429" in error_str:
            return "Search service rate limit exceeded (429 Too Many Requests)"
        if "401" in error_str or "unauthorized" in error_lower:
            return "Search service authentication failed (401 Unauthorized)"
        if "403" in error_str or "forbidden" in error_lower:
            return "Search service access denied (403 Forbidden)"
        if "502" in error_str:
            return "Search service unavailable (502 Bad Gateway)"
        if "503" in error_str:
            return "Search service temporarily unavailable (503 Service Unavailable)"
        if "504" in error_str:
            return "Search service timeout (504 Gateway Timeout)"

        # Generic connection / timeout errors (checked after semantic matches)
        if "connection refused" in error_lower:
            return "Cannot connect to search service"
        if "connectionerror" in error_lower and "apiconnectionerror" not in error_lower:
            return "Cannot connect to search service"
        if "timeouterror" in error_lower or "timed out" in error_lower:
            return "Search request timeout"

        if "jsondecode" in error_lower or "expecting value" in error_lower:
            return "Search service returned invalid response"

        error_type = type(e).__name__
        short_msg = error_str[:100] if len(error_str) > 100 else error_str
        return f"{error_type}: {short_msg}"

    async def multi_query_parallel_search(
        self,
        queries: list[str],
        results_per_query: int,
        time_range: str | None = None,
    ) -> list[tuple[str, list[Document], Exception | None]]:
        """Multi-query parallel search

        Pure parallel search execution, returns raw results. Data processing handled by caller.

        Args:
            queries: List of queries
            results_per_query: Number of results per query
            time_range: Time window the agent explicitly asked for; applies to every query.

        Returns:
            Raw search results list: [(query, documents list, possible exception), ...]

        Raises:
            RuntimeError: When all search queries fail, raises concise error message
        """
        results = await asyncio.gather(*(self.search_and_process(q, results_per_query, time_range) for q in queries))

        # Check if there are successful queries
        successful_queries = [q for q, docs, err in results if err is None and docs]
        failed_queries = [(q, err) for q, _, err in results if err is not None]

        if successful_queries:
            return results

        if failed_queries:
            details = [(q, self._extract_key_error(err)) for q, err in failed_queries]
            primary_ctx = None
            for _, err in failed_queries:
                if isinstance(err, SearchAPIError):
                    primary_ctx = err.context
                    break
            first_error = failed_queries[0][1]
            key_error = self._extract_key_error(first_error)
            raise AllQueriesFailedError(
                f"Web search failed: {key_error}",
                failed_queries=details,
                primary_context=primary_ctx,
            )

        empty_queries = [q for q, docs, err in results if err is None and not docs]
        if empty_queries:
            # A time filter can only have emptied the results if a provider this config can reach maps it.
            if time_range and any(resolve_time_range(time_range, name).params for name in self.config.provider_names):
                cause = (
                    f"The time_range '{time_range}' may have excluded every result: widen or drop it and retry. "
                    "Otherwise the search service may be unreachable or returned an empty response."
                )
            else:
                cause = "The search service may be unreachable or returned an empty response."
            raise AllQueriesFailedError(
                f"Web search returned 0 results for {len(empty_queries)} queries. {cause}",
                failed_queries=[(q, "empty result set") for q in empty_queries],
            )

        raise AllQueriesFailedError("Web search failed: no queries were executed", failed_queries=[])
