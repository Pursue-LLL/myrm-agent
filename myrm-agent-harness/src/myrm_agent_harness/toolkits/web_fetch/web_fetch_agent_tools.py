"""Web fetch meta-tool

Contains:
1. create_web_fetch_tool: Web fetch tool (reads known URLs in full; adds fetch_and_extract when retrieval services are configured)

[INPUT]
- toolkits.retriever.embedding.factory::EmbeddingConfig
- toolkits.retriever.reranker.factory::RerankerConfig
- toolkits.retriever.engine::RetrieverManager (POS: Hybrid retrieval manager for fetched pages) [lazy]
- toolkits.retriever.sufficiency (POS: Retrieval Sufficiency Guard)
- toolkits.web_fetch.processing.full_content_delivery::FetchedPage, plan_full_content, all_failed_content (POS: One shared budget for every fetched page) [lazy]
- toolkits.web_fetch.processing.spill::store_full_text, emit_web_fetch_evicted_ref (POS: Sandbox persistence of the full text) [lazy]
- toolkits.web_fetch.processing.content_sanitize::strip_base64_images_from_markdown (POS: Inline image payload removal) [lazy]
- utils.context_format::wrap_with_external_sources_tag (POS: UNTRUSTED_DATA boundary around fetched content) [lazy]
- toolkits.web_fetch._web_fetch_tool_description::resolve_web_fetch_tool_description
- utils.errors::ToolError, ToolErrorCategory

[OUTPUT]
- create_web_fetch_tool: Create web fetch meta-tool

[POS]
Web fetch meta-tool for known-URL full read and RAG extract modes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from urllib.parse import urlparse

from langchain.tools import BaseTool, tool
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from myrm_agent_harness.core.config.llm import LLMConfig
    from myrm_agent_harness.toolkits.retriever.embedding.factory import EmbeddingConfig
    from myrm_agent_harness.toolkits.retriever.reranker.factory import RerankerConfig
    from myrm_agent_harness.toolkits.retriever.sufficiency import SufficiencyConfig
    from myrm_agent_harness.toolkits.web_fetch.processing.spill import StoredFullText

from myrm_agent_harness.toolkits.web_fetch._web_fetch_tool_description import resolve_web_fetch_tool_description
from myrm_agent_harness.utils.errors import ToolError, ToolErrorCategory

_MAX_URLS_PER_FULL_READ = 5
_REASON_DESCRIPTION = "State your reasoning, express key info with minimal tokens, max 100 chars"


class _FullContentInput(BaseModel):
    urls: list[str] = Field(
        description="Real webpage URL list (up to 5)", min_length=1, max_length=_MAX_URLS_PER_FULL_READ
    )
    reason: str = Field(description=_REASON_DESCRIPTION)


class _FetchOrExtractInput(BaseModel):
    urls: list[str] = Field(description="Real webpage URL list", min_length=1)
    operation: str = Field(default="fetch_and_extract", description="Operation type (default 'fetch_and_extract')")
    questions: list[str] = Field(
        default_factory=list,
        description="Retrieval query list (fetch_and_extract only, 1-5 queries)",
        max_length=5,
    )
    reason: str = Field(description=_REASON_DESCRIPTION)


def create_web_fetch_tool(
    reranker_config: RerankerConfig | None = None,
    embedding_config: EmbeddingConfig | None = None,
    *,
    use_raw_markdown: bool = False,
    allow_private_networks: bool = False,
    sufficiency_config: SufficiencyConfig | None = None,
    sufficiency_llm_config: LLMConfig | None = None,
    blocked_hostnames: tuple[str, ...] | None = None,
    description_locale: str | None = None,
) -> BaseTool:
    """Create web fetch meta-tool.

    Without retrieval services the tool reads the given pages in full (``urls``
    only). With both a reranker and an embedding service it also offers
    ``fetch_and_extract`` and takes an ``operation`` argument.

    ``blocked_hostnames`` is an optional hostname blocklist (exact or ``*.``
    wildcard patterns). When set, URLs whose host matches a pattern are
    rejected before fetching — a generic content policy hook callers can use
    for benchmark decontamination or domain filtering. None disables it.

    ``description_locale`` selects the LLM-facing tool description locale
    (default English).
    """
    tool_description = resolve_web_fetch_tool_description(
        reranker_config is not None and embedding_config is not None, description_locale
    )

    def check_urls(urls: list[str]) -> None:
        _validate_urls(urls, blocked_hostnames=blocked_hostnames, allow_private_networks=allow_private_networks)

    async def read_in_full(urls: list[str]) -> dict[str, object]:
        return await _fetch_full_content(
            urls, use_raw_markdown=use_raw_markdown, allow_private_networks=allow_private_networks
        )

    if reranker_config is None or embedding_config is None:

        @tool("web_fetch_tool", description=tool_description, args_schema=_FullContentInput)
        async def full_content_tool(urls: list[str], reason: str = "") -> dict[str, object]:
            """Read the pages in full."""
            check_urls(urls)
            return await read_in_full(urls)

        return full_content_tool

    @tool("web_fetch_tool", description=tool_description, args_schema=_FetchOrExtractInput)
    async def fetch_or_extract_tool(
        urls: list[str],
        operation: str = "fetch_and_extract",
        questions: list[str] | None = None,
        reason: str = "",
    ) -> dict[str, object]:
        """Read the pages in full, or retrieve the snippets that answer ``questions``."""
        check_urls(urls)
        if operation == "fetch_full_content":
            return await read_in_full(urls)

        if not questions:
            raise ToolError(
                "'questions' parameter is required for fetch_and_extract operation",
                user_hint="Provide 1-5 search queries in the 'questions' parameter.",
            )
        result = await _fetch_and_extract(
            urls,
            questions,
            reranker_config,
            embedding_config,
            allow_private_networks=allow_private_networks,
        )
        await _append_sufficiency_notice(result, questions, sufficiency_config, sufficiency_llm_config)
        return result

    return fetch_or_extract_tool


def _validate_urls(
    urls: list[str],
    *,
    blocked_hostnames: tuple[str, ...] | None,
    allow_private_networks: bool,
) -> None:
    """Refuse URLs that the host blocklist, SSRF guard or exfiltration check does not allow, before any request."""
    if blocked_hostnames:
        from myrm_agent_harness.toolkits.browser.domain_filter import DomainBlocklist

        blocklist = DomainBlocklist.from_strings(blocked_hostnames)
        for url in urls:
            hostname = (urlparse(url).hostname or "").lower()
            if blocklist.is_blocked(hostname):
                raise ToolError(
                    f"URL blocked: {url}",
                    user_hint="The URL host is excluded from fetching. Use a different URL.",
                    error_code="BENCHMARK_BLOCKED_HOST",
                    diagnostic_info={
                        "error_category": ToolErrorCategory.BENCHMARK_BLOCKED.value,
                        "hostname": hostname,
                    },
                )

    if allow_private_networks:
        return

    from myrm_agent_harness.core.security.guards.ssrf import validate_url_for_ssrf
    from myrm_agent_harness.utils.logger_utils import get_agent_logger
    from myrm_agent_harness.utils.url_utils import check_url_exfiltration, sanitize_url_for_error

    for url in urls:
        verdict = validate_url_for_ssrf(url)
        if not verdict.safe:
            raise ToolError(
                f"URL blocked (SSRF protection): {verdict.error} — {url}",
                user_hint="The URL is blocked for security reasons. Use a different, publicly accessible URL.",
            )

        exfiltration_warnings = check_url_exfiltration(url, allow_private_networks=allow_private_networks)
        if exfiltration_warnings:
            logger = get_agent_logger(__name__)
            safe_url = sanitize_url_for_error(url)
            logger.warning(" Potential data exfiltration detected in URL: %s", safe_url)
            for warning in exfiltration_warnings:
                logger.warning(" - %s", warning)
            raise ToolError(
                f"URL blocked (data exfiltration detection): {'; '.join(exfiltration_warnings)} — {safe_url}",
                user_hint="The URL appears to contain sensitive data. Remove secrets from the URL.",
            )


async def _fetch_full_content(
    urls: list[str],
    *,
    use_raw_markdown: bool = False,
    allow_private_networks: bool = False,
) -> dict[str, object]:
    """Read the pages in full: each keeps its share of one budget and the rest stays one file read away."""
    from myrm_agent_harness.toolkits.web_fetch import FetchEngine, web_fetch_tools
    from myrm_agent_harness.toolkits.web_fetch.processing.content_sanitize import strip_base64_images_from_markdown
    from myrm_agent_harness.toolkits.web_fetch.processing.full_content_delivery import (
        FetchedPage,
        all_failed_content,
        plan_full_content,
    )
    from myrm_agent_harness.toolkits.web_fetch.processing.spill import emit_web_fetch_evicted_ref, store_full_text
    from myrm_agent_harness.utils.context_format import wrap_with_external_sources_tag

    need_custom_engine = use_raw_markdown or allow_private_networks
    engine = (
        FetchEngine(
            use_raw_markdown=use_raw_markdown,
            allow_private_networks=allow_private_networks,
            session_vault=web_fetch_tools._http_fetcher._session_vault,
        )
        if need_custom_engine
        else web_fetch_tools
    )
    success_results, failed_results = await engine.crawl_many(urls, max_chars=0)

    if not success_results and not failed_results:
        raise ToolError(
            "No results returned from crawl",
            user_hint="The URLs may be unreachable or blocked. Verify the URLs are correct and publicly accessible.",
        )

    failed_urls = [url for url, _ in failed_results]
    if not success_results:
        return _full_content_result(all_failed_content(failed_urls), sources=[], truncated=False, raw_chars=0)

    sources: list[dict[str, object]] = []
    pages: list[FetchedPage] = []
    for url, doc in success_results:
        page_url = doc.metadata.get("url", url)
        title = doc.metadata.get("title", "")
        sources.append({"url": page_url, "title": title})
        pages.append(
            FetchedPage(
                url=str(page_url),
                title=str(title or ""),
                body=strip_base64_images_from_markdown(doc.page_content),
            )
        )
    delivery = plan_full_content(pages, failed_urls)

    stored = None
    if delivery.stored_text is not None:
        stored = await store_full_text(delivery.stored_text, delivery.read_ranges)

    content = wrap_with_external_sources_tag(delivery.visible_text, source="web_fetch")
    if stored is not None:
        # Outside the untrusted boundary: the guide is ours, not page content.
        content += stored.read_guide
        await emit_web_fetch_evicted_ref(
            stored.evicted_ref,
            stored_chars=stored.stored_chars,
            total_lines=stored.total_lines,
            storage_truncated=stored.storage_truncated,
        )
    return _full_content_result(
        content,
        sources=sources,
        truncated=delivery.truncated,
        raw_chars=delivery.raw_chars,
        stored=stored,
    )


def _full_content_result(
    content: str,
    *,
    sources: list[dict[str, object]],
    truncated: bool,
    raw_chars: int,
    stored: StoredFullText | None = None,
) -> dict[str, object]:
    return {
        "content": content,
        "metadata": {
            "sources": sources,
            "operation": "fetch_full_content",
            "truncated": truncated,
            "raw_chars": raw_chars,
        },
        "evicted_ref": stored.evicted_ref if stored else None,
        "evicted_stored_chars": stored.stored_chars if stored else None,
        "evicted_total_lines": stored.total_lines if stored else None,
        "evicted_storage_truncated": stored.storage_truncated if stored else False,
    }


async def _fetch_and_extract(
    urls: list[str],
    questions: list[str],
    reranker_config: RerankerConfig,
    embedding_config: EmbeddingConfig,
    *,
    allow_private_networks: bool = False,
) -> dict[str, object]:
    """Retrieve relevant content snippets from webpages."""
    from myrm_agent_harness.toolkits.retriever.embedding.factory import get_embedding_service
    from myrm_agent_harness.toolkits.retriever.engine import RetrieverManager
    from myrm_agent_harness.toolkits.retriever.reranker.factory import get_reranker_service
    from myrm_agent_harness.utils.context_format import wrap_with_external_sources_tag

    reranker = get_reranker_service(reranker_config)
    embeddings = get_embedding_service(embedding_config)
    url_metadata_list, formatted_context, error = await RetrieverManager().retrieve_from_urls(
        urls=urls,
        questions=questions,
        reranker=reranker,
        embeddings=embeddings,
        top_k=10,
        allow_private_networks=allow_private_networks,
    )

    if error:
        raise ToolError(
            f"Fetch failed: {error}",
            user_hint="The fetch operation failed. Check if the URLs are valid and the pages are accessible.",
        )
    if not formatted_context:
        raise ToolError(
            "No relevant content found in the provided URLs",
            user_hint="The pages were fetched but no content matched the queries. Try broader or different questions.",
        )

    return {
        "content": wrap_with_external_sources_tag(formatted_context, source="web_fetch"),
        "metadata": {
            "sources": url_metadata_list,
            "operation": "fetch_and_extract",
            "questions": questions,
        },
    }


async def _append_sufficiency_notice(
    result: dict[str, object],
    questions: list[str],
    sufficiency_config: SufficiencyConfig | None,
    sufficiency_llm_config: LLMConfig | None,
) -> None:
    """When the extracted snippets look insufficient for ``questions``, tell the model what is missing."""
    content = result.get("content")
    if not (
        sufficiency_config
        and sufficiency_config.enabled
        and sufficiency_llm_config
        and isinstance(content, str)
        and content
    ):
        return

    from myrm_agent_harness.toolkits.retriever.sufficiency import evaluate_sufficiency

    verdict = await evaluate_sufficiency(
        query=" | ".join(questions),
        snippets=content,
        llm_config=sufficiency_llm_config,
        config=sufficiency_config,
    )
    if verdict.is_sufficient or verdict.confidence < sufficiency_config.confidence_threshold:
        return

    guidance_parts: list[str] = []
    if verdict.missing_aspects:
        guidance_parts.append("**Missing information**: " + "; ".join(verdict.missing_aspects))
    if verdict.suggested_queries:
        guidance_parts.append(
            "**Suggested follow-up searches**: " + ", ".join(f'"{q}"' for q in verdict.suggested_queries)
        )
    if verdict.negative_constraint_violations:
        guidance_parts.append(
            "**Exclusion violations** (user requested these be excluded): "
            + "; ".join(verdict.negative_constraint_violations)
        )
    if guidance_parts:
        notice = "\n\n---\n⚠️ **Retrieval Sufficiency Notice**: The extracted content may be incomplete.\n"
        result["content"] = content + notice + "\n".join(guidance_parts)

    metadata = result.get("metadata")
    if isinstance(metadata, dict):
        metadata["sufficiency"] = {
            "is_sufficient": verdict.is_sufficient,
            "confidence": verdict.confidence,
            "missing_aspects": list(verdict.missing_aspects),
            "suggested_queries": list(verdict.suggested_queries),
            "negative_constraint_violations": list(verdict.negative_constraint_violations),
        }
