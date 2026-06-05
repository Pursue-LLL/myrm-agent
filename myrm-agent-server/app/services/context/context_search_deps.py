"""Dependencies for unified context search."""

from __future__ import annotations

from fastapi import Depends
from myrm_agent_harness.toolkits.memory import MemoryManager

from app.api.memory.utils import get_crud_memory_manager
from app.services.context.context_search_service import ContextSearchService
from app.services.local_file_search.service import get_local_file_search_service


async def build_context_search_service(
    memory_manager: MemoryManager = Depends(get_crud_memory_manager),
) -> ContextSearchService:
    svc = get_local_file_search_service()
    if not svc.is_initialized:
        await svc.initialize()
    return ContextSearchService(
        memory_manager=memory_manager,
        file_engine=svc.search_engine,
    )
