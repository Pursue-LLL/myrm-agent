"""[POS]: app/schemas/batch_learn.py
[INPUT]: None.
[OUTPUT]: Pydantic schemas for batch memory learning requests, per-item namespaced responses, and undo operations.
"""

from pydantic import BaseModel, Field


class BatchChunkDTO(BaseModel):
    """Input chunk representation for batch extraction."""

    chunk_index: int = Field(..., ge=0, description="Sequential chunk index")
    raw_text: str = Field(..., min_length=1, description="Raw text segment undergoing memory distillation")
    metadata: dict[str, str | int | float | bool] = Field(
        default_factory=dict, description="Arbitrary provenance metadata"
    )


class BatchLearnRequest(BaseModel):
    """Payload to initiate resilient batch learning across multiple chunks."""

    chunks: list[BatchChunkDTO] = Field(..., min_length=1, description="List of raw text chunks")
    scope: str = Field(default="default", description="Top-level isolation scope (e.g. project name)")
    sub_scope: str = Field(default="global", description="Sub-scope (e.g. user ID or agent ID)")
    category: str = Field(default="general", description="Cognitive category of the extracted knowledge")


class LearnedItemDTO(BaseModel):
    """Serialized representation of a learned canonical memory item with its unique namespaced ID."""

    namespaced_id: str = Field(..., description="Canonical namespaced memory identifier")
    batch_id: str = Field(..., description="Parent batch execution ID")
    chunk_index: int = Field(..., description="Source chunk index")
    content: str = Field(..., description="Extracted memory content")
    tags: list[str] = Field(default_factory=list, description="Associated tags")
    layer_recommendation: str = Field(..., description="Recommended cognitive layer")
    status: str = Field(..., description="Current status: active or revoked")
    created_at: float = Field(..., description="Timestamp of creation")


class ChunkDiagnosticDTO(BaseModel):
    """Diagnostics tracking resilience, retry count, and latency per chunk."""

    chunk_index: int = Field(..., description="Source chunk index")
    status: str = Field(..., description="Chunk processing status")
    attempt_count: int = Field(..., description="Number of execution attempts")
    elapsed_ms: float = Field(..., description="Execution duration in milliseconds")
    extracted_items_count: int = Field(..., description="Count of successfully distilled items")


class BatchLearnResponse(BaseModel):
    """Summary of batch learning execution containing both per-item namespaced IDs and resilience telemetry."""

    batch_id: str = Field(..., description="Batch identifier")
    total_chunks: int = Field(..., description="Total chunks processed")
    successful_chunks: int = Field(..., description="Chunks that succeeded on first attempt")
    retried_chunks: int = Field(..., description="Chunks that succeeded after transient retries")
    failed_chunks: int = Field(..., description="Chunks that failed permanently")
    total_items_learned: int = Field(..., description="Total learned memory items produced")
    items: list[LearnedItemDTO] = Field(default_factory=list, description="Extracted memory items")
    chunk_diagnostics: list[ChunkDiagnosticDTO] = Field(default_factory=list, description="Per-chunk diagnostics")


class UndoItemRequest(BaseModel):
    """Request to revoke a specific memory item by its namespaced ID."""

    namespaced_id: str = Field(..., description="Target namespaced ID to revoke")


class UndoItemResponse(BaseModel):
    """Result of revoking an individual namespaced memory item."""

    success: bool = Field(..., description="Whether revocation succeeded")
    namespaced_id: str = Field(..., description="Target namespaced ID")
    message: str = Field(..., description="Human-readable result status")


class BatchItemsResponse(BaseModel):
    """Collection of memory items produced under a single batch."""

    batch_id: str = Field(..., description="Parent batch ID")
    total_items: int = Field(..., description="Total items count")
    items: list[LearnedItemDTO] = Field(default_factory=list, description="Items array")
