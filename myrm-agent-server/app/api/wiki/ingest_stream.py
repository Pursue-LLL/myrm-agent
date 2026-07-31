"""Wiki ingest SSE stream route registration.

[INPUT]
- app.api.dependencies::get_optional_llm_for_user (POS: optional LLM for wiki compile)
- app.services.wiki.ingest_events::wiki_ingest_event_bus (POS: wiki ingest SSE hub)

[OUTPUT]
- register_ingest_stream_routes: attaches GET /ingest/stream SSE endpoint
- get_wiki_archiver_for_ingest_stream: scoped archiver dependency for SSE route

[POS]
HTTP SSE boundary for Settings wiki ingest live updates without full-page polling.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from langchain_core.language_models import BaseChatModel
from myrm_agent_harness.toolkits.memory import MemoryManager

from app.api.dependencies import get_optional_llm_for_user
from app.api.memory.utils import get_optional_memory_manager
from app.schemas.streaming import SSE_RESPONSE_HEADERS
from app.services.wiki import MemoryToWikiArchiver
from app.services.wiki.ingest_events import normalize_agent_scope_key, wiki_ingest_event_bus


async def get_wiki_archiver_for_ingest_stream(
    llm: Annotated[BaseChatModel, Depends(get_optional_llm_for_user)],
    manager: Annotated[MemoryManager | None, Depends(get_optional_memory_manager)],
    agent_id: Annotated[str | None, Query(description="Agent whose wiki vault to use")] = None,
) -> MemoryToWikiArchiver:
    from app.services.wiki.vault_service import get_wiki_archiver

    return get_wiki_archiver(llm, manager, agent_id=agent_id)


def register_ingest_stream_routes(router: APIRouter) -> None:
    @router.get("/ingest/stream")
    async def stream_wiki_ingest_events(
        archiver: Annotated[MemoryToWikiArchiver, Depends(get_wiki_archiver_for_ingest_stream)],
        agent_id: Annotated[str | None, Query(description="Agent whose wiki vault to use")] = None,
    ) -> StreamingResponse:
        scope_key = normalize_agent_scope_key(agent_id)
        return StreamingResponse(
            wiki_ingest_event_bus.stream_scope(scope_key, archiver, agent_id),
            media_type="text/event-stream",
            headers=SSE_RESPONSE_HEADERS,
        )
