"""
[POS] app/api/memory/zero_llm_memory_router.py
[INPUT] fastapi, app/schemas/zero_llm_memory.py, app/services/memory/zero_llm_memory_service.py
[OUTPUT] router

FastAPI router for Zero-LLM deterministic local memory capture and FTS graph retrieval.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from app.schemas.zero_llm_memory import (
    ZeroLlmExtractRequest,
    ZeroLlmExtractResponse,
    ZeroLlmSearchRequest,
    ZeroLlmSearchResponse,
    ZeroLlmStatsResponse,
)
from app.services.memory.zero_llm_memory_service import (
    ZeroLlmMemoryService,
    get_zero_llm_memory_service,
)

router = APIRouter(prefix="/zero-llm", tags=["memory-zero-llm"])


@router.post(
    "/extract",
    response_model=ZeroLlmExtractResponse,
    status_code=status.HTTP_200_OK,
    summary="Extract operational facts deterministically with zero model token cost",
)
def extract_facts(
    req: ZeroLlmExtractRequest,
    service: ZeroLlmMemoryService = Depends(get_zero_llm_memory_service),
) -> ZeroLlmExtractResponse:
    """Extract deterministic facts from text, tool outputs, or conversation turns."""
    return service.extract_facts(req)


@router.post(
    "/search",
    response_model=ZeroLlmSearchResponse,
    status_code=status.HTTP_200_OK,
    summary="Search memory with SQLite FTS5 lexical matching and 1-hop [[Wikilink]] graph traversal",
)
def search_memory(
    req: ZeroLlmSearchRequest,
    service: ZeroLlmMemoryService = Depends(get_zero_llm_memory_service),
) -> ZeroLlmSearchResponse:
    """Search memory pages and linked entities with zero LLM API calls."""
    return service.search(req)


@router.get(
    "/stats",
    response_model=ZeroLlmStatsResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve operational telemetry and zero-cost verification statistics",
)
def get_stats(
    service: ZeroLlmMemoryService = Depends(get_zero_llm_memory_service),
) -> ZeroLlmStatsResponse:
    """Get Zero-LLM engine statistics and token cost metrics."""
    return service.get_stats()
