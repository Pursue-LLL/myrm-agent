"""Pydantic schemas for Git-native OKF v0.2 knowledge bundles.

[INPUT]
- pydantic::{BaseModel, Field} (POS: validated request and response models)

[OUTPUT]
- LoadBundleRequestDTO, LoadBundleResponseDTO: bundle loading
- OKFSearchRequestDTO, OKFSearchResultDTO: concept search
- OKFConceptDetailDTO, ConceptSummaryItemDTO, OKFDisclosureSummaryDTO: concept detail and progressive-disclosure summary
- OKFValidationReportDTO: conformance and staleness report

[POS]
API contracts of the Git-native OKF knowledge bundle feature, shared by its router and service.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class LoadBundleRequestDTO(BaseModel):
    """Payload to load an OKF v0.2 knowledge bundle from a filesystem directory."""

    bundle_path: str = Field(description="Filesystem directory path containing OKF .md concepts")


class LoadBundleResponseDTO(BaseModel):
    """Result of loading and indexing an OKF v0.2 knowledge bundle."""

    bundle_path: str = Field(description="Normalized path to the loaded bundle root")
    loaded_concepts_count: int = Field(ge=0, description="Total concept markdown files parsed and indexed")
    is_success: bool = Field(description="True if bundle was loaded successfully")


class OKFSearchRequestDTO(BaseModel):
    """Query parameters for in-memory BM25 lexical retrieval."""

    query: str = Field(min_length=1, description="Search keywords or concepts")
    limit: int = Field(default=10, ge=1, le=100, description="Maximum number of hits to return")
    filter_governance: str | None = Field(default=None, description="Optional governance filter: constraint|hold|context")
    filter_status: str | None = Field(default=None, description="Optional status filter: draft|stable|deprecated")


class OKFSearchResultDTO(BaseModel):
    """Ranked hit from BM25 sub-millisecond lexical search."""

    concept_id: str = Field(description="Bundle-relative concept ID (without .md)")
    title: str = Field(description="Concept title")
    type: str = Field(description="Concept type (e.g. rule, architecture, standard)")
    description: str = Field(description="Summary description")
    governance: str = Field(description="Governance level (constraint, hold, or context)")
    score: float = Field(ge=0.0, description="BM25 relevance score")
    matched_fields: list[str] = Field(default_factory=list, description="Fields matching query terms")
    tags: list[str] = Field(default_factory=list, description="Categorical tags")
    code_refs: list[str] = Field(default_factory=list, description="Associated source paths or globs")
    is_stale: bool = Field(description="True if concept has exceeded its stale_after date")


class OKFConceptDetailDTO(BaseModel):
    """Full concept detail card for phase-two deep inspection."""

    id: str = Field(description="Bundle-relative concept ID")
    path: str = Field(description="Relative path with .md")
    type: str = Field(description="Concept type")
    title: str = Field(description="Concept title")
    description: str = Field(description="Concept description")
    governance: str = Field(description="Governance level")
    status: str = Field(description="Concept lifecycle status")
    stale_after: str = Field(description="Staleness cutoff date YYYY-MM-DD")
    code_refs: list[str] = Field(default_factory=list, description="Associated codebase references")
    tags: list[str] = Field(default_factory=list, description="Categorical tags")
    body: str = Field(description="Full markdown content after frontmatter")
    is_stale: bool = Field(description="True if concept has expired")


class OKFValidationReportDTO(BaseModel):
    """Audit report for bundle conformance, shelf-life rot, and anti-tamper trust."""

    bundle_path: str = Field(description="Target bundle directory path")
    declared_version: str = Field(description="Declared OKF specification version")
    concept_count: int = Field(ge=0, description="Total concepts evaluated")
    errors: list[str] = Field(default_factory=list, description="Fatal structural errors")
    warnings: list[str] = Field(default_factory=list, description="Non-fatal warnings")
    gate_findings: list[str] = Field(default_factory=list, description="Security or governance gate violations")
    stale_count: int = Field(ge=0, description="Number of expired concepts")
    superseded_trust_count: int = Field(ge=0, description="Number of human signatures superseded by agent modifications")
    is_conformant: bool = Field(description="True if all structural requirements are satisfied")
    gate_passed: bool = Field(description="True if zero errors and zero gate findings")


class ConceptSummaryItemDTO(BaseModel):
    """Lightweight item for two-phase progressive disclosure."""

    id: str = Field(description="Concept identifier")
    title: str = Field(description="Concept title")
    description: str = Field(description="Brief summary")
    governance: str = Field(description="Governance level")
    status: str = Field(description="Lifecycle status")
    is_stale: bool = Field(description="True if expired")
    code_refs: list[str] = Field(default_factory=list, description="Code references")


class OKFDisclosureSummaryDTO(BaseModel):
    """First-phase progressive disclosure card (~300 tokens footprint)."""

    bundle_path: str = Field(description="Bundle root directory path")
    total_concepts: int = Field(ge=0, description="Total active concepts")
    stale_count: int = Field(ge=0, description="Count of expired concepts")
    concepts: list[ConceptSummaryItemDTO] = Field(default_factory=list, description="Summary cards")
