"""Data transfer objects for incremental sliding window Markdown chunker API.

[POS]
Pydantic contracts for slicing Markdown documents, performing incremental diff indexing,
evaluating token savings, and context hydration.

[INPUT]
- datetime, typing, pydantic

[OUTPUT]
- ChunkingConfigDTO, MarkdownChunkDTO, ChunkSliceRequest, ChunkSliceResponse
- IncrementalDiffReportDTO, IncrementalIndexRequest, IncrementalIndexResponse
- HydrateRequest, HydrateResponse
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field


class ChunkingConfigDTO(BaseModel):
    """Configuration DTO for sliding window Markdown chunking."""

    target_tokens: int = Field(default=400, gt=0, description="Target token budget per chunk")
    overlap_tokens: int = Field(
        default=80, ge=0, description="Overlap token budget across consecutive chunks"
    )
    chars_per_token: float = Field(
        default=3.5, gt=0.0, description="Character-to-token heuristic ratio"
    )
    max_chunk_chars: int = Field(
        default=2400, gt=0, description="Maximum character cap per chunk"
    )


class MarkdownChunkDTO(BaseModel):
    """Data transfer representation of a structured Markdown chunk."""

    chunk_id: str = Field(description="Unique identifier for chunk")
    source_path: str = Field(description="Origin document path")
    start_line: int = Field(ge=1, description="1-based starting line number in source")
    end_line: int = Field(ge=1, description="1-based ending line number in source")
    char_start: int = Field(ge=0, description="0-based character start index in source")
    char_end: int = Field(ge=0, description="0-based character end index in source")
    text: str = Field(description="Chunk textual content")
    chunk_hash: str = Field(description="Deterministic SHA256 prefix of text")
    token_estimate: int = Field(ge=0, description="Estimated token count")
    is_truncated: bool = Field(default=False, description="True if truncated by max character cap")


class ChunkSliceRequest(BaseModel):
    """Payload to slice Markdown content into semantic chunks."""

    content: str = Field(description="Raw Markdown text to slice")
    source_path: str = Field(default="MEMORY.md", description="Source path identifier")
    config: ChunkingConfigDTO | None = Field(default=None, description="Optional custom chunking config")


class ChunkSliceResponse(BaseModel):
    """Outcome of Markdown chunk slicing."""

    source_path: str = Field(description="Origin document path")
    total_chunks: int = Field(ge=0, description="Total chunks generated")
    chunks: list[MarkdownChunkDTO] = Field(description="Generated chunks")


class IncrementalDiffReportDTO(BaseModel):
    """Report detailing incremental chunk diff and token savings."""

    source_path: str = Field(description="Target document path")
    total_chunks: int = Field(ge=0, description="Total chunks in updated document")
    reused_chunks: int = Field(ge=0, description="Count of identical chunks reused from cache")
    changed_chunks: int = Field(ge=0, description="Count of new or modified chunks needing embedding")
    deleted_chunks: int = Field(ge=0, description="Count of obsolete chunks removed")
    token_savings_pct: float = Field(
        ge=0.0, le=100.0, description="Percentage of embedding API tokens saved via reuse"
    )
    status: Literal["unchanged", "partially_updated", "fully_reindexed"] = Field(
        description="Diff outcome status"
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Diff calculation timestamp",
    )


class IncrementalIndexRequest(BaseModel):
    """Payload to perform incremental diff indexing on updated Markdown content."""

    source_path: str = Field(description="Target document path")
    new_content: str = Field(description="Updated document content")
    config: ChunkingConfigDTO | None = Field(default=None, description="Optional custom chunking config")


class IncrementalIndexResponse(BaseModel):
    """Outcome of incremental indexing with token savings metrics."""

    report: IncrementalDiffReportDTO = Field(description="Incremental diff analysis report")
    chunks: list[MarkdownChunkDTO] = Field(description="All chunks representing updated document")


class HydrateRequest(BaseModel):
    """Payload to hydrate context around a specific chunk."""

    chunk: MarkdownChunkDTO = Field(description="Target chunk with line pointers")
    full_document: str = Field(description="Complete source document text")
    window_lines: int = Field(default=3, ge=0, description="Number of context lines to expand")


class HydrateResponse(BaseModel):
    """Hydrated context response."""

    hydrated_text: str = Field(description="Expanded surrounding document context")
    window_lines: int = Field(ge=0, description="Number of context lines expanded")
    start_line: int = Field(ge=1, description="1-based starting line of chunk")
    end_line: int = Field(ge=1, description="1-based ending line of chunk")
