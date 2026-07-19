"""Unified knowledge recall across memory and wiki vaults.

[INPUT]
- myrm_agent_harness.toolkits.memory::MemoryManager (POS: long-term memory retrieval)
- myrm_agent_harness.toolkits.memory.memory_citations::emit_cited_memory_ids (POS: SSE citation bridge)
- Callable wiki query backend bound to the active agent vault

[OUTPUT]
- create_knowledge_recall_tool(): EXTENDED LangChain tool with corpus=memory|wiki|all

[POS]
Server business tool mounted when both memory and wiki are enabled for an agent.
Does not replace COMMON memory_recall_tool (Prompt Cache anchor).
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from typing import Annotated, Literal

from langchain.tools import tool
from langchain_core.tools import BaseTool
from myrm_agent_harness.toolkits.memory import MemoryManager
from myrm_agent_harness.toolkits.memory.memory_citations import cited_memory_ref, emit_cited_memory_ids
from myrm_agent_harness.toolkits.memory.memory_recall_budget import (
    DEFAULT_RECALL_LIMIT,
    MAX_RECALL_OUTPUT_CHARS,
    budget_recall_line,
    line_cost,
    normalize_recall_limit,
)
from myrm_agent_harness.toolkits.memory.memory_recall_formatting import (
    channel_label as _channel_label,
)
from myrm_agent_harness.toolkits.memory.memory_recall_formatting import (
    is_stale as _is_stale,
)
from myrm_agent_harness.toolkits.memory.memory_recall_formatting import (
    memory_age_label,
)
from myrm_agent_harness.toolkits.memory.types import (
    ClaimMemory,
    MemorySearchResult,
    MemoryType,
    SemanticMemory,
)
from pydantic import BaseModel, Field

Corpus = Literal["memory", "wiki", "all"]

_CODE_PATH_PATTERN = re.compile(
    r"(\/[a-zA-Z0-9_\-\.]+)+\/?|[a-zA-Z0-9_\-\.]+\.(py|ts|tsx|js|jsx|json|yaml|yml|md|rs|go|java|c|cpp|h|hpp)"
)

_DRIFT_DEFENSE_FOOTER = (
    "\n---\n"
    "Note: Before acting on recalled memories:\n"
    "- If a memory references files/functions → verify they still exist\n"
    "- If a memory states configs/versions → check current project state\n"
    "- If a memory conflicts with current observations → trust current observation\n"
    "To fix outdated memories: use memory_manage(action='correct') or memory_manage(action='delete')"
)

_CATEGORY_TO_TYPE: dict[str, MemoryType] = {
    "knowledge": MemoryType.SEMANTIC,
    "claim": MemoryType.CLAIM,
    "event": MemoryType.EPISODIC,
    "preference": MemoryType.PROFILE,
    "rule": MemoryType.PROCEDURAL,
}


class KnowledgeRecallInput(BaseModel):
    query: str = Field(..., min_length=1, description="Question or search query")
    corpus: Corpus = Field(
        default="all",
        description="Search memory only, wiki only, or both (default all)",
    )
    limit: int = Field(
        default=DEFAULT_RECALL_LIMIT,
        ge=1,
        le=15,
        description="Max memory hits when corpus includes memory",
    )


_KNOWLEDGE_RECALL_DESCRIPTION = (
    "Search long-term memory and/or the agent wiki knowledge base in one call. "
    "Use corpus=all when the user mixes personal context with uploaded documents. "
    "Use corpus=memory for preferences and past conversations; corpus=wiki for PDFs and notes."
)


async def _emit_memory_citations(
    manager: MemoryManager,
    displayed_results: list[MemorySearchResult],
) -> None:
    ratable_types = (MemoryType.SEMANTIC, MemoryType.EPISODIC)
    cited_ids = [
        result.memory.id
        for result in displayed_results
        if result.memory.id and result.memory_type in ratable_types
    ]
    cited_refs = [
        cited_memory_ref(result.memory, result.memory_type, result.score)
        for result in displayed_results
        if result.memory.id and result.memory_type in ratable_types
    ]
    if cited_ids:
        manager.set_last_cited_memory_ids(cited_ids)
    if cited_ids or manager.last_retrieval_trace is not None:
        await emit_cited_memory_ids(
            cited_ids,
            cited_refs,
            tool_name="knowledge_recall_tool",
            retrieval_trace=manager.last_retrieval_trace,
        )


async def _format_memory_hits(manager: MemoryManager, query: str, limit: int) -> str:
    recall_limit = normalize_recall_limit(limit)
    results = await manager.search(query, limit=recall_limit)

    output: list[str] = []
    displayed_results: list[MemorySearchResult] = []
    max_body_chars = MAX_RECALL_OUTPUT_CHARS - (len(_DRIFT_DEFENSE_FOOTER) if results else 0)
    output_chars = 0
    truncated_by_budget = False

    session = manager.active_session
    if session and session.buffer_size > 0 and query:
        for buffered in session.search_buffer(query):
            budgeted = budget_recall_line(
                prefix="[buffered] ",
                content=buffered.content,
                suffix="",
                output_chars=output_chars,
                max_body_chars=max_body_chars,
            )
            if budgeted.line is None:
                truncated_by_budget = True
                break
            output.append(budgeted.line)
            output_chars = budgeted.next_chars
            truncated_by_budget = truncated_by_budget or budgeted.truncated

    if not results and not output:
        if manager.last_retrieval_trace is not None:
            await emit_cited_memory_ids(
                [],
                [],
                tool_name="knowledge_recall_tool",
                retrieval_trace=manager.last_retrieval_trace,
            )
        return "No relevant memories found."

    for result in results:
        cat = next(
            (key for key, value in _CATEGORY_TO_TYPE.items() if value == result.memory_type),
            result.memory_type.value,
        )
        memory = result.memory
        age = memory_age_label(memory.created_at)
        provenance = _channel_label(memory.scope.channel_id)
        prefix = f"{provenance}[{cat}] (id: {memory.id}, score: {result.score:.2f}, {age}) "
        suffix = ""
        if isinstance(memory, ClaimMemory):
            relation_type = str(memory.metadata.get("latest_relationship_type", "")).strip().lower()
            relation_suffix = f" relation={relation_type}" if relation_type else ""
            suffix += (
                f" [claim_graph freshness={memory.freshness} contradiction={memory.contradiction_status} "
                f"evidence={memory.evidence_count}{relation_suffix}]"
            )
        if isinstance(memory, SemanticMemory) and memory.source_error:
            suffix += f" (avoid: {memory.source_error})"
        if result.memory_type in (MemoryType.SEMANTIC, MemoryType.EPISODIC, MemoryType.CLAIM) and _is_stale(
            memory.created_at
        ):
            if _CODE_PATH_PATTERN.search(memory.content):
                suffix += (
                    "\n[CRITICAL: Outdated memory referencing potential paths. "
                    "YOU MUST USE Read/Grep TOOLS TO VERIFY BEFORE CITING IF AVAILABLE, OR DO NOT BLINDLY TRUST]"
                )
            else:
                suffix += " (may be outdated — verify before citing)"
        budgeted = budget_recall_line(
            prefix=prefix,
            content=result.content,
            suffix=suffix,
            output_chars=output_chars,
            max_body_chars=max_body_chars,
        )
        if budgeted.line is None:
            truncated_by_budget = True
            break
        output.append(budgeted.line)
        displayed_results.append(result)
        output_chars = budgeted.next_chars
        truncated_by_budget = truncated_by_budget or budgeted.truncated

    if truncated_by_budget:
        notice = (
            "[recall_budget] Some recalled content was truncated to keep this tool result within "
            f"{MAX_RECALL_OUTPUT_CHARS} chars. Refine the query or lower limit for more detail."
        )
        if output_chars + line_cost(notice) <= max_body_chars:
            output.append(notice)

    await _emit_memory_citations(manager, displayed_results)

    text = "\n".join(output)
    if displayed_results:
        text += _DRIFT_DEFENSE_FOOTER
    return text


def create_knowledge_recall_tool(
    manager: MemoryManager,
    *,
    query_wiki: Callable[[str], Awaitable[str]],
) -> BaseTool:
    """Create a unified recall tool for memory + wiki corpora."""

    @tool("knowledge_recall_tool", description=_KNOWLEDGE_RECALL_DESCRIPTION, args_schema=KnowledgeRecallInput)
    async def knowledge_recall(
        query: Annotated[str, "Question or search query"],
        corpus: Annotated[Corpus, "memory, wiki, or all"] = "all",
        limit: Annotated[int, "Max memory hits (1-15)"] = DEFAULT_RECALL_LIMIT,
    ) -> str:
        sections: list[str] = []

        if corpus in ("memory", "all"):
            memory_text = await _format_memory_hits(manager, query, limit)
            sections.append(f"## Memory\n{memory_text}")

        if corpus in ("wiki", "all"):
            wiki_answer = await query_wiki(query)
            wiki_body = wiki_answer.strip() or "No relevant wiki content found."
            sections.append(f"## Wiki\n{wiki_body}")

        return "\n\n".join(sections)

    return knowledge_recall
