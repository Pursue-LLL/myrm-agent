"""Incremental sliding window Markdown chunker API router.

[POS]
FastAPI endpoints for slicing Markdown documents, performing incremental diff
indexing with token savings metrics, and expanding context hydration.

[INPUT]
- fastapi (APIRouter, Depends, status)
- app.schemas.markdown_chunker (
    ChunkSliceRequest,
    ChunkSliceResponse,
    HydrateRequest,
    HydrateResponse,
    IncrementalIndexRequest,
    IncrementalIndexResponse,
  )
- app.services.memory.markdown_chunker (
    MarkdownChunkerService,
    get_markdown_chunker_service,
  )

[OUTPUT]
- router: APIRouter with /slice, /incremental-index, and /hydrate endpoints
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from app.schemas.markdown_chunker import (
    ChunkSliceRequest,
    ChunkSliceResponse,
    HydrateRequest,
    HydrateResponse,
    IncrementalIndexRequest,
    IncrementalIndexResponse,
)
from app.services.memory.markdown_chunker import (
    MarkdownChunkerService,
    get_markdown_chunker_service,
)

router = APIRouter(prefix="/chunker", tags=["Memory Markdown Chunker"])


@router.post(
    "/slice",
    response_model=ChunkSliceResponse,
    summary="Slice Markdown text into sliding window semantic chunks",
    status_code=status.HTTP_200_OK,
)
async def slice_markdown_content(
    payload: ChunkSliceRequest,
    service: MarkdownChunkerService = Depends(get_markdown_chunker_service),
) -> ChunkSliceResponse:
    """Slice Markdown document into overlapping semantic chunks with line-level pointers."""
    return await service.slice_markdown(payload)


@router.post(
    "/incremental-index",
    response_model=IncrementalIndexResponse,
    summary="Perform incremental diff indexing and calculate token savings",
    status_code=status.HTTP_200_OK,
)
async def incremental_index_markdown(
    payload: IncrementalIndexRequest,
    service: MarkdownChunkerService = Depends(get_markdown_chunker_service),
) -> IncrementalIndexResponse:
    """Diff updated document against cached chunks and only index modified content."""
    return await service.incremental_index(payload)


@router.post(
    "/hydrate",
    response_model=HydrateResponse,
    summary="Expand surrounding document context around a chunk",
    status_code=status.HTTP_200_OK,
)
async def hydrate_chunk_context(
    payload: HydrateRequest,
    service: MarkdownChunkerService = Depends(get_markdown_chunker_service),
) -> HydrateResponse:
    """Expand document lines around start_line and end_line pointers."""
    return await service.hydrate_context(payload)
