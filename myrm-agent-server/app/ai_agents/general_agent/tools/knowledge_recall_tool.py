"""Unified knowledge recall across memory and wiki vaults.

[INPUT]
- myrm_agent_harness.toolkits.memory::MemoryManager (POS: long-term memory retrieval)
- Callable wiki query backend bound to the active agent vault

[OUTPUT]
- create_knowledge_recall_tool(): EXTENDED LangChain tool with corpus=memory|wiki|all

[POS]
Server business tool mounted when both memory and wiki are enabled for an agent.
Does not replace COMMON memory_recall_tool (Prompt Cache anchor).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Annotated, Literal

from langchain.tools import tool
from langchain_core.tools import BaseTool
from myrm_agent_harness.toolkits.memory import MemoryManager
from myrm_agent_harness.toolkits.memory.memory_recall_budget import (
    DEFAULT_RECALL_LIMIT,
    normalize_recall_limit,
)
from pydantic import BaseModel, Field

Corpus = Literal["memory", "wiki", "all"]


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


async def _format_memory_hits(manager: MemoryManager, query: str, limit: int) -> str:
    recall_limit = normalize_recall_limit(limit)
    results = await manager.search(query, limit=recall_limit)
    if not results:
        return "No relevant memories found."

    lines: list[str] = []
    for result in results:
        content = result.content.strip()
        if len(content) > 800:
            content = content[:800] + "…"
        lines.append(f"[{result.memory_type.value}] {content}")
    return "\n".join(lines)


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
