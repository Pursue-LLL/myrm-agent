"""Wiki ingest SSE stream route registration.

[INPUT]
- app.api.wiki.archiver_dependency::get_scoped_wiki_archiver (POS: archiver bound to the user's model and vault)
- app.services.wiki.ingest_events::wiki_ingest_event_bus (POS: wiki ingest SSE hub)

[OUTPUT]
- register_ingest_stream_routes: attaches GET /ingest/stream SSE endpoint

[POS]
HTTP SSE boundary for Settings wiki ingest live updates without full-page polling.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from app.api.wiki.archiver_dependency import get_scoped_wiki_archiver
from app.schemas.streaming import SSE_RESPONSE_HEADERS
from app.services.wiki import MemoryToWikiArchiver
from app.services.wiki.ingest_events import normalize_agent_scope_key, wiki_ingest_event_bus


def register_ingest_stream_routes(router: APIRouter) -> None:
    @router.get("/ingest/stream")
    async def stream_wiki_ingest_events(
        archiver: Annotated[MemoryToWikiArchiver, Depends(get_scoped_wiki_archiver)],
        agent_id: Annotated[str | None, Query(description="Agent whose wiki vault to use")] = None,
    ) -> StreamingResponse:
        scope_key = normalize_agent_scope_key(agent_id)
        return StreamingResponse(
            wiki_ingest_event_bus.stream_scope(scope_key, archiver, agent_id),
            media_type="text/event-stream",
            headers=SSE_RESPONSE_HEADERS,
        )
