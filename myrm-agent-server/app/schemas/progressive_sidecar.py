"""[POS]: app/schemas/progressive_sidecar.py
[INPUT]: API request/response parameters for L0/L1/L2 progressive context disclosure.
[OUTPUT]: Strongly typed Pydantic models for three-tier sidecars, OKF frontmatter, and read queries.
"""

from enum import StrEnum

from pydantic import BaseModel, Field


class ContextTierAPIEnum(StrEnum):
    """Context granularity tiers exposed via REST API."""

    L0_ABSTRACT = "l0_abstract"
    L1_OVERVIEW = "l1_overview"
    L2_DETAIL = "l2_detail"


class OKFFrontmatterResponse(BaseModel):
    """Open Knowledge Format metadata header response."""

    doc_id: str = Field(..., description="Canonical document or memory URI")
    title: str = Field(default="", description="Document title or section label")
    digest_sha256: str = Field(..., description="SHA-256 fingerprint of L2 raw content")
    l0_tokens_est: int = Field(default=0, ge=0, description="Estimated token size of L0 abstract")
    l1_tokens_est: int = Field(default=0, ge=0, description="Estimated token size of L1 overview")
    l2_tokens_est: int = Field(default=0, ge=0, description="Estimated token size of L2 raw content")
    updated_at_epoch: float = Field(..., description="Update epoch timestamp in seconds")


class ProgressiveBundleResponse(BaseModel):
    """Three-tier progressive context bundle response."""

    doc_id: str = Field(..., description="Document identifier")
    frontmatter: OKFFrontmatterResponse = Field(..., description="Structured OKF frontmatter")
    l0_abstract: str = Field(..., description="L0 ultra-compact abstract (~100 tokens)")
    l1_overview: str = Field(..., description="L1 structural skeleton and key contracts (~2k tokens)")
    l2_detail: str = Field(..., description="L2 full verbatim body")
    token_savings_pct: float = Field(default=0.0, ge=0.0, le=100.0, description="Token savings percentage")


class GenerateSidecarsRequest(BaseModel):
    """Request payload to synthesize three-tier sidecars."""

    uri: str = Field(..., description="Target canonical URI")
    content: str = Field(..., description="Raw text payload to analyze")
    title: str = Field(default="", description="Optional title or label")


class WriteWithSidecarsRequest(BaseModel):
    """Request payload to persist document and companion sidecars into VFS."""

    uri: str = Field(..., description="Target document canonical URI")
    content: str = Field(..., description="Raw text payload to persist")
    title: str = Field(default="", description="Optional document title")
    metadata: dict[str, str] = Field(default_factory=dict, description="Metadata tags")


class ReadTieredRequest(BaseModel):
    """Request payload to read context at specified granularity tier."""

    uri: str = Field(..., description="Target document canonical URI")
    tier: ContextTierAPIEnum = Field(default=ContextTierAPIEnum.L0_ABSTRACT, description="Desired granularity tier")


class ReadTieredResponse(BaseModel):
    """Response payload containing sliced context for requested tier."""

    uri: str = Field(..., description="Target document canonical URI")
    tier: str = Field(..., description="Delivered granularity tier")
    content: str = Field(..., description="Delivered content payload")
    token_est: int = Field(default=0, ge=0, description="Estimated token count")
    has_higher_detail: bool = Field(default=True, description="Whether higher detail tiers are available")
