"""Web search tools wrapper


[INPUT]
- web_search.core.common::SearchResult (POS: search result type)
- web_search.processing._explicit_params::ProviderOverride, normalize_explicit_params, apply_tavily_site_constraint (POS: Agent explicit param normalizer)
- web_search.processing.search_results_processor::combine_search_results_unified, apply_domain_diversity_sort, search_results_to_documents (POS: search result merger and domain diversity sorting)
- web_search.providers.web_searcher::WebSearcher, SearchServiceConfig, SearchServiceType (POS: web searcher supporting multiple engines)
- utils.context_format::format_documents_with_metadata (POS: document formatting utility)
- web_search.processing.intent_optimizer::SearchIntent, detect_search_intent, extract_and_pin_structured_identifiers, resolve_search_params (POS: search intent detection and parameter optimization) [lazy]
- web_search.providers.bilibili_search::search_bilibili (POS: Bilibili search fast-path) [lazy]
- web_search.providers.github_code_search::search_github_code (POS: GitHub code search fast-path) [lazy]
- browser.domain_filter::DomainBlocklist (POS: domain pattern matcher shared with the browser domain filter) [lazy]

[OUTPUT]
- WebSearchTools: multi-query web search tool class
- SearchServiceConfig: search service config class (re-export)
- SearchServiceType: search provider slug alias, a plain str (re-export)

[POS]
Web search tools wrapper. As the toolkit's external interface, provides unified web search capability for
Agent and business layer. Every query source (configured provider, Bilibili API, GitHub code search) feeds
one merge pipeline: round-robin interleave across questions -> URL/content dedup -> domain-diversity decay
-> first top_k. No ranking model sits in the path: the search engines' own ordering is the relevance
signal, and the interleave keeps every question represented in the final documents.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol
from urllib.parse import urlparse

from langchain_core.documents import Document

from myrm_agent_harness.toolkits.web_search.core.common import SearchResult
from myrm_agent_harness.toolkits.web_search.processing._explicit_params import (
    ProviderOverride,
    apply_tavily_site_constraint,
    normalize_explicit_params,
)
from myrm_agent_harness.toolkits.web_search.processing.search_results_processor import (
    apply_domain_diversity_sort,
    combine_search_results_unified,
    search_results_to_documents,
)
from myrm_agent_harness.toolkits.web_search.providers.web_searcher import (
    SearchServiceConfig,
    SearchServiceType,
    WebSearcher,
)
from myrm_agent_harness.utils.context_format import format_documents_with_metadata

if TYPE_CHECKING:
    from collections.abc import Awaitable

__all__ = ["SearchServiceConfig", "SearchServiceType", "WebSearchTools"]

logger = logging.getLogger(__name__)

# One entry per question, in the shape combine_search_results_unified consumes: (query, documents, error).
_QueryDocuments = list[tuple[str, list[Document], Exception | None]]


class _NativeSearch(Protocol):
    """A search source that is not the configured provider (Bilibili API, GitHub code search)."""

    def __call__(self, query: str, /, *, max_results: int) -> Awaitable[list[SearchResult] | None]: ...


@dataclass(frozen=True, slots=True)
class _QueryPlan:
    """How each question is searched, derived from intent detection and explicit params."""

    search_queries: list[str]
    overrides: list[ProviderOverride | None]
    bilibili_queries: list[str]
    code_queries: list[str]


class WebSearchTools:
    """Multi-query web search: parallel search -> merge -> format.

    Args:
        config: Search service configuration
        searcher: Pre-built searcher, an alternative to ``config``
    """

    def __init__(
        self,
        config: SearchServiceConfig | None = None,
        *,
        searcher: WebSearcher | None = None,
    ):
        if searcher is not None:
            self._searcher = searcher
        elif config is not None:
            self._searcher = WebSearcher(config)
        else:
            raise ValueError("Either config or searcher must be provided to WebSearchTools")

    async def search(self, query: str, num_results: int = 5) -> list[SearchResult]:
        """Single-query search."""
        return await self._searcher.search(query, num_results)

    async def fast_search_with_questions(
        self,
        questions: list[str],
        search_results_per_query: int = 10,
        top_k: int = 10,
        explicit_params: dict[str, object] | None = None,
        blocked_hostnames: tuple[str, ...] | None = None,
    ) -> tuple[list[dict[str, object]], str]:
        """Search every question in parallel and return one merged, formatted result set.

        All query sources share one merge: results are interleaved round-robin across questions (a question
        cannot be crowded out by the others), deduplicated by URL and content, reordered with domain-diversity
        decay and cut to ``top_k``. With one question the engine's ranking stands; only the same-domain
        decay can move a result down.

        Args:
            questions: Query list (rewritten)
            search_results_per_query: Number of search results per query
            top_k: Final number of documents to return
            explicit_params: Agent-level explicit search parameters (highest priority).
                Supported keys: time_range.
            blocked_hostnames: Optional hostname blocklist (exact or ``*.`` wildcard). Results whose
                URL host matches a pattern are dropped before selection/formatting — a generic content
                policy hook callers can use for benchmark decontamination (e.g. Hugging Face hosts).
                None disables it.

        Returns:
            (sources_metadata, formatted_context). May be empty when every result is filtered out
            by the hostname blocklist — callers treat that as "no usable results", not an error.
        """
        start_time = time.perf_counter()

        plan = _plan_queries(questions, self._searcher.config.search_service, explicit_params)
        per_query_docs = await self._search_per_query(questions, plan, search_results_per_query)
        search_time_ms = (time.perf_counter() - start_time) * 1000

        _, unified_docs = combine_search_results_unified(per_query_docs)
        unified_docs = apply_domain_diversity_sort(unified_docs)
        if blocked_hostnames:
            unified_docs = _drop_blocked_hostname_docs(unified_docs, blocked_hostnames)
        selected_docs = unified_docs[: max(top_k, 0)]

        total_time_ms = (time.perf_counter() - start_time) * 1000
        logger.info(
            f"Search completed: queries={len(questions)}, unified={len(unified_docs)}, "
            f"selected={len(selected_docs)}, search_time={search_time_ms:.0f}ms, total={total_time_ms:.0f}ms"
        )

        if total_time_ms > 5000:
            logger.warning(f"Slow search detected: {total_time_ms:.0f}ms for {len(questions)} queries")

        sources_metadata, formatted_context, truncation_stats = format_documents_with_metadata(
            selected_docs,
            questions=questions,
        )

        if truncation_stats:
            logger.info(
                f"Token usage: {truncation_stats.original_tokens}→{truncation_stats.final_tokens}, "
                f"retention={truncation_stats.retention_ratio:.1%}"
            )

        return sources_metadata, formatted_context

    async def _search_per_query(
        self,
        questions: list[str],
        plan: _QueryPlan,
        results_per_query: int,
    ) -> _QueryDocuments:
        """Search every question and return its documents.

        Uses a native source when all questions target it (Bilibili API, GitHub code search) and falls back
        to the configured provider when that source returns nothing. Every route yields per-question
        documents, so the merge treats them identically.
        """
        if plan.bilibili_queries and len(plan.bilibili_queries) == len(questions):
            from myrm_agent_harness.toolkits.web_search.providers.bilibili_search import search_bilibili

            per_query = await _search_natively(plan.bilibili_queries, search_bilibili, results_per_query)
            if per_query:
                logger.info(f"Bilibili fast-path: {len(plan.bilibili_queries)} queries, {_count_docs(per_query)} docs")
                return per_query
            logger.info("Bilibili fast-path failed, falling back to generic search with site:bilibili.com")
            fallback_questions = [f"{q} site:bilibili.com" for q in questions]
            return await self._searcher.multi_query_parallel_search(
                fallback_questions, results_per_query, [None] * len(fallback_questions)
            )

        if plan.code_queries and len(plan.code_queries) == len(questions):
            from myrm_agent_harness.toolkits.web_search.providers.github_code_search import search_github_code

            per_query = await _search_natively(plan.code_queries, search_github_code, results_per_query)
            if per_query:
                logger.info(f"GitHub code fast-path: {len(plan.code_queries)} queries, {_count_docs(per_query)} docs")
                return per_query
            logger.info("GitHub code fast-path yielded no results, falling back to generic search")

        return await self._searcher.multi_query_parallel_search(plan.search_queries, results_per_query, plan.overrides)


def _plan_queries(
    questions: list[str],
    provider: SearchServiceType,
    explicit_params: dict[str, object] | None,
) -> _QueryPlan:
    """Detect intent per question and fuse search params (explicit > intent > config.extra_params)."""
    from myrm_agent_harness.toolkits.web_search.processing.intent_optimizer import (
        SearchIntent,
        detect_search_intent,
        extract_and_pin_structured_identifiers,
        resolve_search_params,
    )

    normalized_explicit = normalize_explicit_params(explicit_params, provider) if explicit_params else None

    search_queries: list[str] = []
    overrides: list[ProviderOverride | None] = []
    bilibili_queries: list[str] = []
    code_queries: list[str] = []
    for q in questions:
        # Pin structured domain identifiers (CVE/DOI/tickers) to preserve exact match
        pinned_q, _ = extract_and_pin_structured_identifiers(q)
        intent_result = detect_search_intent(q)
        if intent_result.intent == SearchIntent.PLATFORM_BILIBILI:
            bilibili_queries.append(pinned_q)
        elif intent_result.intent == SearchIntent.CODE:
            code_queries.append(pinned_q)
        override = resolve_search_params(intent_result, provider)

        # Fusion: explicit_params > intent_optimizer > config.extra_params
        if normalized_explicit:
            override = {**(override or {}), **normalized_explicit}

        search_query = pinned_q
        if provider == "tavily":
            search_query, override = apply_tavily_site_constraint(pinned_q, override)

        search_queries.append(search_query)
        overrides.append(override)
        if override:
            logger.info(
                f"Intent detected: query='{q[:50]}' intent={intent_result.intent.value} "
                f"confidence={intent_result.confidence:.2f} override={override}"
            )

    return _QueryPlan(
        search_queries=search_queries,
        overrides=overrides,
        bilibili_queries=bilibili_queries,
        code_queries=code_queries,
    )


async def _search_natively(
    queries: list[str],
    search: _NativeSearch,
    results_per_query: int,
) -> _QueryDocuments:
    """Query a non-provider source once per query.

    Queries the source returns nothing for are omitted, so an empty list means the source is unusable
    and the caller falls back to the configured provider.
    """
    per_query: _QueryDocuments = []
    for query in queries:
        results = await search(query, max_results=results_per_query)
        if results:
            per_query.append((query, search_results_to_documents(results), None))
    return per_query


def _count_docs(per_query_docs: _QueryDocuments) -> int:
    return sum(len(docs) for _, docs, _ in per_query_docs)


def _drop_blocked_hostname_docs(
    documents: list[Document],
    blocked_hostnames: tuple[str, ...],
) -> list[Document]:
    """Drop documents whose URL host matches the blocklist (exact or ``*.`` wildcard).

    Applied to the merged search results before selection/formatting so filtered hosts never
    surface in the LLM context — a generic content policy hook (benchmark decontamination
    uses it to hide Hugging Face results that may carry reference material).
    """
    from myrm_agent_harness.toolkits.browser.domain_filter import DomainBlocklist

    blocklist = DomainBlocklist.from_strings(blocked_hostnames)
    kept: list[Document] = []
    dropped = 0
    for doc in documents:
        hostname = (urlparse(str((doc.metadata or {}).get("url") or "")).hostname or "").lower()
        if hostname and blocklist.is_blocked(hostname):
            dropped += 1
            continue
        kept.append(doc)
    if dropped:
        logger.info(
            "Hostname blocklist dropped %d search result(s) before formatting",
            dropped,
        )
    return kept
