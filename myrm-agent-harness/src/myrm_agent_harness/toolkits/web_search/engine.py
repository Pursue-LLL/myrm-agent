"""Web search tools wrapper


[INPUT]
- web_search.core.common::SearchResult (POS: search result type)
- web_search.core.exceptions::AllQueriesFailedError (POS: Search exception types)
- web_search.processing.identifier_pinning::pin_structured_identifiers (POS: exact-phrase pinning of CVE ids and DOIs)
- web_search.processing.search_results_processor::combine_search_results_unified, apply_domain_diversity_sort, search_results_to_documents (POS: search result merger and domain diversity sorting)
- web_search.providers.bilibili_search::is_bilibili_video_query, search_bilibili (POS: Bilibili search fast-path)
- web_search.providers.web_searcher::WebSearcher, SearchServiceConfig, SearchServiceType (POS: web searcher supporting multiple engines)
- core.context_vars::source_indexer_var (POS: the run's source numbering, so the numbers a result prints are the indexes of its cards)
- utils.context_format::format_documents_with_metadata (POS: document formatting utility)
- browser.domain_filter::DomainBlocklist (POS: domain pattern matcher shared with the browser domain filter) [lazy]

[OUTPUT]
- WebSearchTools: multi-query web search tool class; the sources it returns name the provider that returned them (``search_provider``)
- SearchServiceConfig: search service config class (re-export)
- SearchServiceType: search provider slug alias, a plain str (re-export)

[POS]
Web search tools wrapper. As the toolkit's external interface, provides unified web search capability for
Agent and business layer. Every query source (configured provider, Bilibili API) feeds one merge pipeline:
round-robin interleave across questions -> URL/content dedup -> domain-diversity decay -> first top_k. No
ranking model sits in the path: the search engines' own ordering is the relevance signal; the interleave gives each
question a turn, and the decay and the top_k cut decide which documents survive. A question reaches the provider as
written, except for exact-phrase identifier pinning; each hop maps the agent's explicit time range and ``site:``
operators itself.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from urllib.parse import urlparse

from langchain_core.documents import Document

from myrm_agent_harness.core.context_vars import source_indexer_var
from myrm_agent_harness.toolkits.web_search.core.common import SearchResult
from myrm_agent_harness.toolkits.web_search.core.exceptions import AllQueriesFailedError
from myrm_agent_harness.toolkits.web_search.processing.identifier_pinning import pin_structured_identifiers
from myrm_agent_harness.toolkits.web_search.processing.search_results_processor import (
    apply_domain_diversity_sort,
    combine_search_results_unified,
    search_results_to_documents,
)
from myrm_agent_harness.toolkits.web_search.providers import bilibili_search
from myrm_agent_harness.toolkits.web_search.providers.web_searcher import (
    SearchServiceConfig,
    SearchServiceType,
    WebSearcher,
)
from myrm_agent_harness.utils.context_format import format_documents_with_metadata

__all__ = ["SearchServiceConfig", "SearchServiceType", "WebSearchTools"]

logger = logging.getLogger(__name__)

# One entry per question, in the shape combine_search_results_unified consumes: (query, documents, error).
_QueryDocuments = list[tuple[str, list[Document], Exception | None]]


@dataclass(frozen=True, slots=True)
class _QueryPlan:
    """How each question is searched.

    ``bilibili_scoped`` holds when every question is scoped to Bilibili videos, so the Bilibili API can answer them.
    """

    search_queries: list[str]
    bilibili_scoped: bool


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
        time_range: str | None = None,
        blocked_hostnames: tuple[str, ...] | None = None,
    ) -> tuple[list[dict[str, object]], str]:
        """Search every question in parallel and return one merged, formatted result set.

        All query sources share one merge: results are interleaved round-robin across questions (each question
        takes turns), deduplicated by URL and content, reordered with domain-diversity decay and cut to ``top_k``,
        so the decay and the cut decide which documents survive. With one question the engine's ranking stands; only
        the same-domain decay can move a result down.

        Args:
            questions: Query list (rewritten)
            search_results_per_query: Number of search results per query
            top_k: Final number of documents to return
            time_range: Time window the agent explicitly asked for (day/week/month/year or
                YYYY-MM-DD..YYYY-MM-DD). Every provider hop applies it in its own parameters, or leaves it
                out when it cannot (see ``resolve_time_range``).
            blocked_hostnames: Optional hostname blocklist (exact or ``*.`` wildcard). Results whose
                URL host matches a pattern are dropped before selection/formatting — a generic content
                policy hook callers can use for benchmark decontamination (e.g. Hugging Face hosts).
                None disables it.

        Returns:
            (sources_metadata, formatted_context). A source names the provider whose search returned it under
            ``search_provider``. Both may be empty when every result is filtered out by the hostname blocklist —
            callers treat that as "no usable results", not an error.
        """
        start_time = time.perf_counter()

        plan = _plan_queries(questions)
        per_query_docs = await self._search_per_query(plan, search_results_per_query, time_range)
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
            index_for=source_indexer_var.get(),
        )
        _attach_search_providers(sources_metadata, selected_docs)

        if truncation_stats:
            logger.info(
                f"Token usage: {truncation_stats.original_tokens}→{truncation_stats.final_tokens}, "
                f"retention={truncation_stats.retention_ratio:.1%}"
            )

        return sources_metadata, formatted_context

    async def _search_per_query(
        self,
        plan: _QueryPlan,
        results_per_query: int,
        time_range: str | None,
    ) -> _QueryDocuments:
        """Search every question and return its documents.

        When every question is scoped to Bilibili videos by ``site:`` the Bilibili API answers them all at once, and
        the provider search takes over, with the questions as written, for those it returns nothing for. The
        request to the API carries no date parameter, so an explicit ``time_range`` skips it and the provider search
        carries the constraint. Every route yields per-question documents, so the merge treats them identically.
        """
        if plan.bilibili_scoped and not time_range:
            return await self._search_bilibili_first(plan.search_queries, results_per_query)
        return await self._searcher.multi_query_parallel_search(
            plan.search_queries, results_per_query, time_range=time_range
        )

    async def _search_bilibili_first(
        self,
        queries: list[str],
        results_per_query: int,
    ) -> _QueryDocuments:
        """Answer the questions from the Bilibili API; the provider search takes those it returned nothing for.

        When the provider search fails for them, the questions the API answered stand and the others are left out,
        as a failed question is in the provider route. When the API answered none, the provider's error surfaces.
        """
        api_docs = await _search_bilibili(queries, results_per_query)
        unanswered = [i for i, docs in enumerate(api_docs) if docs is None]
        logger.info(f"Bilibili fast-path answered {len(queries) - len(unanswered)} of {len(queries)} queries")

        provider_results: dict[int, tuple[str, list[Document], Exception | None]] = {}
        if unanswered:
            try:
                results = await self._searcher.multi_query_parallel_search(
                    [queries[i] for i in unanswered], results_per_query
                )
            except AllQueriesFailedError:
                if len(unanswered) == len(queries):
                    raise
                logger.warning(
                    f"Provider search failed for {len(unanswered)} question(s) the Bilibili API could not answer"
                )
            else:
                provider_results = dict(zip(unanswered, results, strict=True))

        per_query: _QueryDocuments = []
        for i, (query, docs) in enumerate(zip(queries, api_docs, strict=True)):
            if docs is not None:
                per_query.append((query, docs, None))
            elif i in provider_results:
                per_query.append(provider_results[i])
        return per_query


def _plan_queries(questions: list[str]) -> _QueryPlan:
    """Pin identifiers in every question and note whether every question is scoped to Bilibili videos."""
    return _QueryPlan(
        search_queries=[pin_structured_identifiers(q) for q in questions],
        bilibili_scoped=bool(questions) and all(bilibili_search.is_bilibili_video_query(q) for q in questions),
    )


async def _search_bilibili(queries: list[str], results_per_query: int) -> list[list[Document] | None]:
    """Query the Bilibili API for every query at once, one entry per query.

    A query the API returns nothing for is ``None``, so the caller can hand just those to the provider.
    """
    answers = await asyncio.gather(
        *(bilibili_search.search_bilibili(query, max_results=results_per_query) for query in queries)
    )
    return [search_results_to_documents(results) if results else None for results in answers]


def _attach_search_providers(sources: list[dict[str, object]], documents: list[Document]) -> None:
    """Name on each source the provider whose search returned it.

    The shared document formatter builds source entries without it. The web_search tool reads the tags to state how
    the providers that served the results handled the agent's constraints, then removes them from the sources it
    returns. Documents that share a URL form one source, which takes the provider of the first of them that names
    one.
    """
    provider_by_url: dict[str, str] = {}
    for doc in documents:
        provider = doc.metadata.get("search_provider")
        if isinstance(provider, str):
            provider_by_url.setdefault(str(doc.metadata.get("url", "")), provider)
    for source in sources:
        if provider := provider_by_url.get(str(source["url"])):
            source["search_provider"] = provider


def _drop_blocked_hostname_docs(
    documents: list[Document],
    blocked_hostnames: tuple[str, ...],
) -> list[Document]:
    """Drop documents whose URL host matches the blocklist (exact or ``*.`` wildcard).

    Applied to the merged search results before selection/formatting so filtered hosts never
    surface in the LLM context — a generic content policy hook (benchmark decontamination
    uses it to hide Hugging Face results that may carry reference material). Results show the
    provider's own URL, and a blocklist entry names a site rather than its ``www.`` alias, so the
    leading ``www.`` is ignored when matching.
    """
    from myrm_agent_harness.toolkits.browser.domain_filter import DomainBlocklist

    blocklist = DomainBlocklist.from_strings(blocked_hostnames)
    kept: list[Document] = []
    dropped = 0
    for doc in documents:
        hostname = (urlparse(str((doc.metadata or {}).get("url") or "")).hostname or "").lower().removeprefix("www.")
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
