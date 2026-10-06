"""Pydantic schemas for System Prompt Anti-Extraction, JIT Sharding, and Canary Sentinel.

[POS] app/schemas/prompt_anti_extraction.py
[INPUT] pydantic
[OUTPUT] PromptShardSchema, RegisterShardsRequest, AssemblePromptRequest, AssemblePromptResponse, AuditExtractionRequest, AuditExtractionResponse
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class PromptShardSchema(BaseModel):
    """Pydantic representation of an instruction shard."""

    model_config = ConfigDict(extra="forbid")

    shard_id: str = Field(..., min_length=1, max_length=64, description="Unique shard ID")
    category: str = Field(..., description="Shard category: CORE_BASE, STAGE_RULE, or PRIVATE_CONSTRAINT")
    content: str = Field(..., min_length=1, max_length=10000, description="Directive content")
    applicable_stages: list[str] = Field(default_factory=list, description="List of task stages where shard applies")
    is_confidential: bool = Field(default=False, description="Whether shard contains sensitive enterprise IP")


class RegisterShardsRequest(BaseModel):
    """Payload to register multiple modular instruction shards."""

    model_config = ConfigDict(extra="forbid")

    shards: list[PromptShardSchema] = Field(..., description="List of instruction shards")


class AssemblePromptRequest(BaseModel):
    """Payload to assemble active JIT system prompt for a stage."""

    model_config = ConfigDict(extra="forbid")

    current_stage: str | None = Field(default=None, description="Active execution stage")
    inject_canary: str | None = Field(default=None, description="Optional session canary token to inject")


class AssemblePromptResponse(BaseModel):
    """Response containing assembled active system prompt."""

    model_config = ConfigDict(extra="forbid")

    assembled_prompt: str
    total_shards_registered: int


class DetectExtractionProbeRequest(BaseModel):
    """Payload to scan user prompt for extraction probe attempts."""

    model_config = ConfigDict(extra="forbid")

    user_text: str = Field(..., min_length=1, max_length=4000, description="User utterance to evaluate")


class DetectExtractionProbeResponse(BaseModel):
    """Evaluation result for prompt extraction probe."""

    model_config = ConfigDict(extra="forbid")

    is_extraction_attempt: bool
    matched_pattern: str | None = None
    safe_fallback_response: str


class ScanStreamingChunkRequest(BaseModel):
    """Payload to scan an outbound streaming chunk for canary leakage."""

    model_config = ConfigDict(extra="forbid")

    chunk: str = Field(..., description="Outbound streaming chunk text")
    canary_token: str = Field(..., min_length=1, max_length=128, description="Session canary token to monitor")


class ScanStreamingChunkResponse(BaseModel):
    """Scan outcome for a streaming chunk."""

    model_config = ConfigDict(extra="forbid")

    canary_detected: bool
    tripped: bool
    scrubbed_chunk: str
    alert_reason: str | None = None


class ScrubOutboundRequest(BaseModel):
    """Payload to scrub confidential directives and canary tokens from outbound text."""

    model_config = ConfigDict(extra="forbid")

    text: str = Field(..., description="Raw text payload to scrub")
    canary_token: str | None = Field(default=None, description="Canary token to redact")
    confidential_snippets: list[str] = Field(
        default_factory=list,
        description="Confidential strings to redact",
    )


class ScrubOutboundResponse(BaseModel):
    """Cleaned outbound text payload."""

    model_config = ConfigDict(extra="forbid")

    scrubbed_text: str
