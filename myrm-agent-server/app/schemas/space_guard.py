"""Pydantic schemas for embedding model dimension and vector space guard API.

[POS]
Data transfer objects for pre-flight vector space validation, model fingerprinting,
space binding, status diagnostics, and re-indexing workflows.

[INPUT]
- typing, pydantic

[OUTPUT]
- SpaceFingerprintDTO, SpaceValidateRequest, SpaceValidateResponse
- SpaceBindRequest, SpaceBindResponse, SpaceStatusResponse
- SpaceReindexRequest, SpaceReindexResponse
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class SpaceFingerprintDTO(BaseModel):
    """Data transfer model for embedding model fingerprint."""

    provider_id: str = Field(description="Embedding provider identifier, e.g. openai, ollama")
    model_name: str = Field(description="Embedding model name, e.g. text-embedding-3-small")
    vector_dimension: int = Field(gt=0, description="Coordinate vector dimension")
    metric_type: Literal["cosine", "dot", "euclidean"] = Field(
        default="cosine", description="Distance metric for similarity calculation"
    )
    config_hash: str = Field(default="", description="Deterministic configuration hash")


class SpaceValidateRequest(BaseModel):
    """Payload for validating vector space compatibility before write/search operations."""

    collection: str = Field(description="Target vector collection name")
    fingerprint: SpaceFingerprintDTO = Field(description="Runtime model fingerprint")
    auto_bind_if_empty: bool = Field(
        default=False, description="If true, registers fingerprint if collection is uninitialized"
    )


class SpaceValidateResponse(BaseModel):
    """Outcome of vector space consistency verification."""

    is_valid: bool = Field(description="Whether runtime model is safe to execute on collection")
    status: str = Field(description="Status code: consistent, dimension_mismatch, model_base_mismatch, etc.")
    message: str = Field(description="Explanatory diagnostic message")
    recommended_action: str = Field(description="Prescribed action: proceed, reindex_required, fallback_fts, etc.")
    expected_fingerprint: SpaceFingerprintDTO | None = Field(
        default=None, description="Registered collection fingerprint"
    )
    current_fingerprint: SpaceFingerprintDTO | None = Field(
        default=None, description="Current runtime fingerprint"
    )


class SpaceBindRequest(BaseModel):
    """Payload for binding or updating collection space metadata."""

    collection: str = Field(description="Target collection name")
    fingerprint: SpaceFingerprintDTO = Field(description="Target model fingerprint")
    total_vectors_indexed: int = Field(default=0, ge=0, description="Initial indexed vector count")


class SpaceBindResponse(BaseModel):
    """Response confirming space fingerprint registration."""

    collection: str = Field(description="Target collection name")
    fingerprint: SpaceFingerprintDTO = Field(description="Registered model fingerprint")
    status: str = Field(default="bound", description="Registration status")


class SpaceStatusResponse(BaseModel):
    """Diagnostic status report of collection vector space."""

    collection: str = Field(description="Target collection name")
    has_registered_space: bool = Field(description="Whether collection space metadata is established")
    fingerprint: SpaceFingerprintDTO | None = Field(
        default=None, description="Registered model fingerprint"
    )
    total_vectors_indexed: int = Field(default=0, ge=0, description="Total indexed vectors")
    last_validated_at: str | None = Field(default=None, description="ISO timestamp of last verification")


class SpaceReindexRequest(BaseModel):
    """Payload to trigger safe vector space migration and re-indexing."""

    collection: str = Field(description="Target collection name")
    target_fingerprint: SpaceFingerprintDTO = Field(description="Target model fingerprint")
    sample_items: list[str] = Field(
        default_factory=list, description="Sample items to re-embed and index"
    )


class SpaceReindexResponse(BaseModel):
    """Outcome of vector space re-indexing."""

    collection: str = Field(description="Target collection name")
    status: str = Field(description="Reindex status: completed, failed, in_progress")
    reindexed_count: int = Field(default=0, ge=0, description="Count of items successfully reindexed")
    error_message: str | None = Field(default=None, description="Error details if migration failed")
