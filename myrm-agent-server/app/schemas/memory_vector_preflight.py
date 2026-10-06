"""
[POS] app/schemas/memory_vector_preflight.py
[INPUT] pydantic
[OUTPUT] SanitizeEndpointRequestDTO, SanitizeEndpointResponseDTO, VerifyDimensionsRequestDTO, DimensionIntegrityReportDTO, InspectVectorStoreRequestDTO, InspectVectorStoreResponseDTO

Pydantic DTOs for Vector Store Preflight Dimension Integrity and IPv4 Loopback Sanitizer.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class SanitizeEndpointRequestDTO(BaseModel):
    """Payload to normalize an endpoint and sanitize IPv6 localhost traps."""

    model_config = ConfigDict(extra="forbid")

    endpoint: str = Field(..., min_length=1, description="Raw host or URI endpoint (e.g. localhost:6333, http://localhost:6333)")


class SanitizeEndpointResponseDTO(BaseModel):
    """Result of endpoint loopback sanitization."""

    model_config = ConfigDict(extra="forbid")

    raw_endpoint: str = Field(..., description="Original raw endpoint string provided")
    sanitized_endpoint: str = Field(..., description="Sanitized IPv4-safe endpoint string")
    was_modified: bool = Field(..., description="Whether the endpoint required loopback sanitization")
    modification_reason: str = Field(default="", description="Explanation of why modification occurred")


class VerifyDimensionsRequestDTO(BaseModel):
    """Payload to rigidly assert vector dimension compatibility."""

    model_config = ConfigDict(extra="forbid")

    actual_dims: int = Field(..., description="Actual output vector length from embedding model (e.g. 1536, 2560)")
    expected_dims: int = Field(..., description="Expected vector size defined on target collection schema")
    embedder_name: str = Field(default="configured_embedder", description="Human-readable embedding model name")
    collection_name: str = Field(default="default_memories", description="Target collection identifier")


class DimensionIntegrityReportDTO(BaseModel):
    """Report outlining dimension match/mismatch preflight status and remediation instructions."""

    model_config = ConfigDict(extra="forbid")

    is_valid: bool = Field(..., description="Whether embedding dimensions match collection schema")
    actual_dims: int = Field(..., description="Actual dimension count")
    expected_dims: int = Field(..., description="Expected dimension count")
    status: str = Field(..., description="Evaluation status: healthy, mismatch_blocked, or invalid_configuration")
    diagnosis: str = Field(..., description="Human-readable diagnosis of dimension alignment")
    suggested_action: str = Field(default="", description="Actionable remediation steps if mismatched")


class InspectVectorStoreRequestDTO(BaseModel):
    """Composite preflight inspection request combining endpoint sanitization and dimension check."""

    model_config = ConfigDict(extra="forbid")

    endpoint: str = Field(..., min_length=1, description="Vector store host or URL endpoint")
    actual_dims: int = Field(..., description="Actual embedding vector dimensions")
    expected_dims: int = Field(..., description="Expected collection dimensions")
    embedder_name: str = Field(default="configured_embedder", description="Embedding model name")
    collection_name: str = Field(default="default_memories", description="Collection name")


class InspectVectorStoreResponseDTO(BaseModel):
    """Comprehensive preflight check result."""

    model_config = ConfigDict(extra="forbid")

    endpoint_result: SanitizeEndpointResponseDTO = Field(..., description="Endpoint normalization result")
    dimension_report: DimensionIntegrityReportDTO = Field(..., description="Dimension compatibility report")
    overall_status: str = Field(..., description="Overall flight status: ready, action_required, or blocked")
