"""
[POS] app/api/memory/code_memory_compaction_router.py
[INPUT] app/schemas/code_memory_compaction.py, app/services/memory/code_memory_compaction_service.py
[OUTPUT] router
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.schemas.code_memory_compaction import (
    CodeCompactionRequest,
    CodeCompactionResponse,
    SingleSkeletonRequest,
    SingleSkeletonResponse,
)
from app.services.memory.code_memory_compaction_service import (
    CodeMemoryCompactionService,
    get_code_memory_compaction_service,
)

router = APIRouter(prefix="/compaction/code", tags=["code_memory_compaction"])


@router.post(
    "/compact",
    response_model=CodeCompactionResponse,
    summary="Compact codebase memories under token budget",
)
def compact_code_memory(
    request: CodeCompactionRequest,
    service: CodeMemoryCompactionService = Depends(get_code_memory_compaction_service),
) -> CodeCompactionResponse:
    """Compact multiple code files or symbols to satisfy a target token budget."""
    return service.compact(request)


@router.post(
    "/skeleton",
    response_model=SingleSkeletonResponse,
    summary="Extract AST skeleton for a single snippet",
)
def extract_code_skeleton(
    request: SingleSkeletonRequest,
    service: CodeMemoryCompactionService = Depends(get_code_memory_compaction_service),
) -> SingleSkeletonResponse:
    """Extract structural interface signatures (L1) or control flow (L2) for a snippet."""
    return service.extract_skeleton(request)
