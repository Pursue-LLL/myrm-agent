"""Web search meta-tool


[INPUT]
- toolkits.web_search.engine::SearchServiceConfig, WebSearchTools (POS: Web search tools wrapper, the toolkit's external interface) [WebSearchTools lazy]
- toolkits.web_search.processing.citation_resolver::enrich_sources_with_resolved_urls (POS: Redirect-chain resolution and tracking-parameter cleanup of source URLs) [lazy]
- toolkits.retriever.sufficiency (POS: Retrieval Sufficiency Guard for quality evaluation)
- toolkits.web_search._web_search_tool_description::resolve_web_search_tool_description (POS: Locale-aware prompt SSOT; recommends fetch_and_extract only when the agent has it)
- toolkits.web_search.processing._explicit_params::describe_time_range_caveats (POS: Explicit constraint mapper; states how the providers that served the results fall short of a requested time range) [lazy]
- core.config.llm::LLMConfig (POS: Framework-agnostic LLM configuration SSOT)
- utils.context_format::wrap_with_external_sources_tag (POS: Context formatting utilities; wraps search text as untrusted data) [lazy]
- utils.errors::ToolError, ToolErrorCategory (POS: Framework-level error handling with structured tool errors)
- langchain.tools::tool (POS: LangChain tool decorator)
- pydantic::BaseModel, Field, field_validator (POS: parameter validation)

[OUTPUT]
- create_web_search_tool: factory function to create web search tool (``fetch_and_extract_available`` tells it whether the agent's web_fetch_tool offers fetch_and_extract); the ``metadata.sources`` it returns are the engine's sources without the internal ``search_provider`` tag

[POS]
Web search meta-tool. Integrates web search capability as a meta-tool (high frequency, 80%+ queries require search).
Supports batch queries, query rewriting, and cost control. Provides real-time information retrieval via
SearchServiceConfig-configured search engines.

When sufficiency evaluation is enabled, post-search results are evaluated for completeness
and negative constraint violations, with guidance appended for the agent to act upon.

Contains:
1. create_web_search_tool: web search tool
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from langchain.tools import BaseTool, tool
from pydantic import BaseModel, Field, field_validator

if TYPE_CHECKING:
    from myrm_agent_harness.core.config.llm import LLMConfig
    from myrm_agent_harness.toolkits.retriever.sufficiency import SufficiencyConfig
    from myrm_agent_harness.toolkits.web_search.engine import SearchServiceConfig

from myrm_agent_harness.toolkits.web_search._web_search_tool_description import (
    resolve_web_search_tool_description,
)
from myrm_agent_harness.utils.errors import ToolError, ToolErrorCategory


def _split_serving_providers(sources: list[dict[str, object]]) -> tuple[list[dict[str, object]], list[str]]:
    """Separate the engine's per-source ``search_provider`` tags from the sources the tool returns.

    The tags only tell this tool which providers answered. Left on the sources they would travel with the stream
    and the stored message, which declare no such field. Returns the untagged sources and the distinct providers
    the tags named, in order of first appearance.
    """
    tags = (source.get("search_provider") for source in sources)
    providers = list(dict.fromkeys(tag for tag in tags if isinstance(tag, str)))
    untagged = [{key: value for key, value in source.items() if key != "search_provider"} for source in sources]
    return untagged, providers


def create_web_search_tool(
    search_service_cfg: SearchServiceConfig,
    sufficiency_config: SufficiencyConfig | None = None,
    sufficiency_llm_config: LLMConfig | None = None,
    *,
    description_locale: str | None = None,
    fetch_and_extract_available: bool = False,
    blocked_terms: tuple[str, ...] | None = None,
    blocked_hostnames: tuple[str, ...] | None = None,
) -> BaseTool:
    """Create a web search meta-tool.

    Args:
        search_service_cfg: Search service configuration
        sufficiency_config: RSG configuration (optional); enables retrieval quality evaluation
        sufficiency_llm_config: LLM config for the sufficiency evaluator (required if sufficiency_config.enabled)
        description_locale: BCP-47 locale for LLM-facing tool description (default English).
        fetch_and_extract_available: True when the same agent mounts a web_fetch_tool that offers the
            ``fetch_and_extract`` operation; the description then recommends it for snippets that lack detail.
        blocked_terms: Optional substring blocklist for search queries. When set, any query
            containing a blocked term (case-insensitive) is rejected before the search runs —
            a generic content policy hook callers can use for benchmark decontamination
            (e.g. Hugging Face references). None disables it.
        blocked_hostnames: Optional hostname blocklist (exact or ``*.`` wildcard) for search
            results. Results whose URL host matches a pattern are dropped before the formatted
            context is built — a generic content policy hook callers can use for benchmark
            decontamination (e.g. Hugging Face hosts). None disables it.

    Returns:
        web_search_tool tool function
    """
    tool_description = resolve_web_search_tool_description(
        description_locale, fetch_and_extract_available=fetch_and_extract_available
    )

    class WebSearchInput(BaseModel):
        questions: list[str] = Field(
            description="Search query list (1-5), must follow query rewriting rules, ensuring independence, self-containment, and multi-dimensionality",
            min_length=1,
            max_length=5,
        )
        reason: str = Field(
            default="",
            description="Search rationale, express key information in minimal tokens, max 100 chars",
        )
        time_range: str | None = Field(
            default=None,
            description="Time range. Set only when the user explicitly mentions a time constraint: day/week/month/year or YYYY-MM-DD..YYYY-MM-DD.",
        )

        @field_validator("questions", mode="before")
        @classmethod
        def convert_string_to_list(cls, v: str | list[str]) -> list[str]:
            """Handle LLM passing comma-separated strings — auto-converts to list."""
            if isinstance(v, str):
                parts = re.split(r"[,，]", v)
                return [q.strip() for q in parts if q.strip()]
            return v

    @tool("web_search_tool", description=tool_description, args_schema=WebSearchInput)
    async def web_search_func(
        questions: list[str],
        reason: str = "",
        time_range: str | None = None,
    ) -> dict[str, object]:
        """Execute web search and return structured results.

        Returns: {"content": "...", "metadata": {...}}
        - content: Formatted text content (for the LLM)
        - metadata: Structured metadata (for business layer, e.g., citation collection)
        """
        from myrm_agent_harness.toolkits.web_search.engine import WebSearchTools

        if blocked_terms:
            lowered_terms = tuple(term.lower() for term in blocked_terms)
            for q in questions:
                if any(term in q.lower() for term in lowered_terms):
                    raise ToolError(
                        f"Search query blocked: {q}",
                        user_hint="The query is excluded from search for this run. Rephrase it without the blocked terms.",
                        error_code="BENCHMARK_BLOCKED_QUERY",
                        diagnostic_info={
                            "error_category": ToolErrorCategory.BENCHMARK_BLOCKED.value,
                            "query": q,
                        },
                    )

        web_search = WebSearchTools(search_service_cfg)
        sources_metadata, formatted_context = await web_search.fast_search_with_questions(
            questions=questions,
            search_results_per_query=10,
            top_k=10,
            time_range=time_range,
            blocked_hostnames=blocked_hostnames,
        )

        from myrm_agent_harness.toolkits.web_search.processing.citation_resolver import (
            enrich_sources_with_resolved_urls,
        )

        sources_metadata, serving_providers = _split_serving_providers(
            await enrich_sources_with_resolved_urls(sources_metadata)
        )

        if formatted_context:
            from myrm_agent_harness.utils.context_format import (
                wrap_with_external_sources_tag,
            )

            content = wrap_with_external_sources_tag(formatted_context, source="web_search")
        else:
            content = formatted_context

        if sufficiency_config and sufficiency_config.enabled and sufficiency_llm_config and content:
            from myrm_agent_harness.toolkits.retriever.sufficiency import (
                evaluate_sufficiency,
            )

            original_query = " | ".join(questions)
            verdict = await evaluate_sufficiency(
                query=original_query,
                snippets=content,
                llm_config=sufficiency_llm_config,
                config=sufficiency_config,
            )

            if not verdict.is_sufficient and verdict.confidence >= sufficiency_config.confidence_threshold:
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
                    notice = "\n\n---\n⚠️ **Retrieval Sufficiency Notice**: The search results may be incomplete.\n"
                    content += notice + "\n".join(guidance_parts)

        # Outside the untrusted-content wrapper: this line is the tool's own statement, not search-result text.
        if time_range and content:
            from myrm_agent_harness.toolkits.web_search.processing._explicit_params import (
                describe_time_range_caveats,
            )

            # The caveat concerns the providers that returned these results, not the ones waiting behind them in
            # the chain; results that name no provider fall back to every configured one.
            providers = serving_providers or search_service_cfg.provider_names
            if caveats := describe_time_range_caveats(time_range, providers):
                content += f"\n\nTime filter notice: {caveats}"

        return {"content": content, "metadata": {"sources": sources_metadata}}

    return web_search_func
