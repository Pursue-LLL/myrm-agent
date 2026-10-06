"""
[POS] app/schemas/memory_provenance_batch.py
[INPUT] pydantic
[OUTPUT] ToolExecutionTraceDTO, ExtractionProvenanceLinkDTO, CreateProvenanceLinkRequestDTO, NamespacedMemoryRefDTO, BatchLearnItemDTO, BatchLearnRequestDTO, BatchLearnResponseDTO

Pydantic DTOs for Skill Memory Extraction Provenance and Batch Learn Namespace Isolator.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ToolExecutionTraceDTO(BaseModel):
    """Forensic record of a tool execution serving as concrete physical evidence."""

    model_config = ConfigDict(extra="forbid")

    tool_name: str = Field(..., description="Name of executed tool")
    tool_call_id: str | None = Field(default=None, description="Model call ID")
    input_args_summary: str = Field(default="", description="Sanitized arguments summary")
    output_evidence_snippet: str = Field(
        default="", description="Sanitized factual output snippet proving execution"
    )
    status: str = Field(default="success", description="Execution status")
    duration_ms: float = Field(default=0.0, ge=0.0, description="Duration in milliseconds")


class ExtractionProvenanceLinkDTO(BaseModel):
    """Provenance link DTO anchoring skill patterns to physical context."""

    model_config = ConfigDict(extra="forbid")

    link_id: str = Field(..., description="Unique provenance link identifier")
    conversation_id: str = Field(..., description="Source conversation ID")
    turn_index: int | None = Field(default=None, ge=0, description="Turn index within conversation")
    trigger_prompt_snippet: str = Field(..., description="User prompt snippet triggering turn")
    tool_traces: list[ToolExecutionTraceDTO] = Field(
        default_factory=list, description="Ordered physical tool executions providing evidence"
    )
    counterexample_snippet: str | None = Field(
        default=None, description="Optional contrastive pitfall observed"
    )
    confidence_score: float = Field(
        default=1.0, ge=0.0, le=1.0, description="Confidence in this extraction provenance"
    )


class CreateProvenanceLinkRequestDTO(BaseModel):
    """Payload to create and anchor an extraction provenance link."""

    model_config = ConfigDict(extra="forbid")

    conversation_id: str = Field(..., description="Source conversation ID")
    trigger_prompt: str = Field(..., description="User prompt or intent trigger text")
    turn_index: int | None = Field(default=None, ge=0, description="Turn index")
    tool_traces: list[ToolExecutionTraceDTO] = Field(
        default_factory=list, description="Ordered tool execution records"
    )
    counterexample: str | None = Field(
        default=None, description="Optional contrastive counterexample"
    )
    confidence_score: float = Field(
        default=1.0, ge=0.0, le=1.0, description="Confidence score"
    )


class NamespacedMemoryRefDTO(BaseModel):
    """Namespaced memory reference guaranteeing cross-scope uniqueness."""

    model_config = ConfigDict(extra="forbid")

    namespaced_id: str = Field(..., description="Scope-prefixed deterministic identifier")
    namespace: str = Field(..., description="Target primary namespace")
    scope_level: str = Field(..., description="Scope classification level")
    raw_id: str = Field(..., description="Original raw memory ID")


class BatchLearnItemDTO(BaseModel):
    """Item to process in batch learning pipeline."""

    model_config = ConfigDict(extra="forbid")

    raw_id: str = Field(..., description="Source memory item ID")
    content: str = Field(..., description="Extracted memory content")
    namespace: str = Field(..., description="Target namespace (e.g. 'agent:coder')")
    scope_level: str = Field(default="agent", description="Target scope classification ('agent', 'shared')")
    provenance_link: ExtractionProvenanceLinkDTO | None = Field(
        default=None, description="Optional evidentiary provenance link"
    )


class BatchLearnRequestDTO(BaseModel):
    """Request payload to process batch learning submissions with namespace isolation."""

    model_config = ConfigDict(extra="forbid")

    items: list[BatchLearnItemDTO] = Field(
        default_factory=list, description="Items to isolate and namespaced-partition"
    )


class BatchLearnResponseDTO(BaseModel):
    """Summary of namespaced batch learning isolation."""

    model_config = ConfigDict(extra="forbid")

    total_items: int = Field(default=0, ge=0, description="Total processed items")
    namespaced_items: list[NamespacedMemoryRefDTO] = Field(
        default_factory=list, description="Partitioned items with collision-free namespaced IDs"
    )
    has_provenance_count: int = Field(
        default=0, ge=0, description="Count of items carrying evidentiary provenance links"
    )
