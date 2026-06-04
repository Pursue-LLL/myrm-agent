"""Agent tool for unified context search."""

from __future__ import annotations

from typing import Annotated

from langchain_core.tools import tool
from myrm_agent_harness.toolkits.memory import MemoryManager
from myrm_agent_harness.toolkits.local_file_search import LocalFileSearchEngine

from app.services.context.context_search_service import ContextSearchService


def create_context_search_tool(
    memory_manager: MemoryManager,
    file_engine: LocalFileSearchEngine | None,
) -> object:
    service = ContextSearchService(memory_manager=memory_manager, file_engine=file_engine)

    @tool("context_search_tool")
    async def context_search(
        query: Annotated[str, "Natural language query to search memories and authorized local files"],
        top_k: Annotated[int, "Maximum merged results (1-20)"] = 8,
    ) -> str:
        """Search both long-term memories and user-authorized local files in one call.

        Use for fuzzy questions that may be answered from past conversations or local documents.
        """
        response = await service.search(query, top_k=min(max(top_k, 1), 20))
        if not response.hits:
            return "No relevant memories or local files found."
        lines: list[str] = []
        for hit in response.hits:
            source_label = "memory" if hit.source == "memory" else "file"
            lines.append(
                f"[{hit.rank}] ({source_label}, score={hit.score:.4f}) {hit.title}\n{hit.snippet}"
            )
        return "\n\n".join(lines)

    return context_search
