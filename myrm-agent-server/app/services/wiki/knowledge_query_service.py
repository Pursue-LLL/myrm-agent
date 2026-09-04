"""Wiki knowledge query SSOT for Settings REST and Chat Wiki Knowledge Lane.

[INPUT]
- app.services.wiki.memory_to_wiki::MemoryToWikiArchiver (POS: Memory→Wiki automatic archiving service)
- app.services.wiki.vault::get_wiki_archiver (POS: shared archiver accessor)
- myrm_agent_harness.toolkits.wiki.retrieval.source_citations::build_wiki_query_sources

[OUTPUT]
- execute_wiki_knowledge_query(): structured answer + citation source dicts

[POS]
Single server-side entry for zero-LLM wiki retrieval used by POST /wiki/query and chat lane.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from langchain_core.language_models.chat_models import BaseChatModel
from myrm_agent_harness.toolkits.wiki.core.types import QueryResult
from myrm_agent_harness.toolkits.wiki.retrieval.source_citations import build_wiki_query_sources

from app.services.agent.llm_access import get_optional_llm_for_user
from app.services.wiki.memory_to_wiki import MemoryToWikiArchiver
from app.services.wiki.vault import get_wiki_archiver

WikiQueryMode = Literal["auto", "raw_claim"]

_EMPTY_ANSWER_FALLBACK = "No relevant wiki content found."


@dataclass(frozen=True, slots=True)
class WikiKnowledgeQueryResult:
    answer: str
    sources: list[dict[str, object]]
    related_articles: list[str]
    confidence_score: float
    retrieval_result: QueryResult


async def resolve_wiki_knowledge_llm(
    *,
    lite_model_cfg: object | None = None,
    model_cfg: object | None = None,
) -> BaseChatModel:
    """Resolve an LLM handle for archiver construction (query path is zero-LLM)."""
    from myrm_agent_harness.toolkits.llms import llm_manager

    chosen_cfg = lite_model_cfg or model_cfg
    if chosen_cfg is not None:
        return await llm_manager.get_llm_from_config(
            chosen_cfg,
            streaming=False,
            api_keys=getattr(chosen_cfg, "api_keys", None),
        )
    return await get_optional_llm_for_user()


async def execute_wiki_knowledge_query(
    *,
    agent_id: str | None,
    question: str,
    query_mode: WikiQueryMode = "auto",
    lite_model_cfg: object | None = None,
    model_cfg: object | None = None,
    llm: BaseChatModel | None = None,
    archiver: MemoryToWikiArchiver | None = None,
    shared_context_ids: list[str] | None = None,
    context_name_map: dict[str, str] | None = None,
) -> WikiKnowledgeQueryResult:
    """Run wiki retrieval and build citation sources (Settings + Chat lane SSOT)."""
    trimmed = question.strip()
    if not trimmed:
        raise ValueError("Wiki question must not be empty")

    active_archiver = archiver
    if active_archiver is None:
        resolved_llm = llm or await resolve_wiki_knowledge_llm(
            lite_model_cfg=lite_model_cfg,
            model_cfg=model_cfg,
        )
        from app.services.wiki.vault import (
            resolve_shared_wiki_vault_labels,
            resolve_shared_wiki_vault_paths,
        )

        public_dirs = list(resolve_shared_wiki_vault_paths(shared_context_ids, must_exist=True))
        public_dir_labels = resolve_shared_wiki_vault_labels(
            shared_context_ids,
            context_name_map=context_name_map,
        )
        active_archiver = get_wiki_archiver(
            resolved_llm,
            manager=None,
            agent_id=agent_id,
            public_dirs=public_dirs,
            public_dir_labels=public_dir_labels,
        )

    result = await active_archiver.query_wiki(trimmed, query_mode=query_mode)
    sources = build_wiki_query_sources(result, structure=active_archiver._structure)
    answer = (result.answer or "").strip() or _EMPTY_ANSWER_FALLBACK
    return WikiKnowledgeQueryResult(
        answer=answer,
        sources=sources,
        related_articles=list(result.related_articles),
        confidence_score=float(result.confidence_score or 0.0),
        retrieval_result=result,
    )
