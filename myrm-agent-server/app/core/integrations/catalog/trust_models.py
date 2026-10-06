"""Trust grading, review provenance, and capability surface data models for Integration Catalog.

[INPUT]
- None (Self-contained domain models for catalog integration trust)

[OUTPUT]
- TrustTier, ReviewStatus, CapabilityScopeRisk, CatalogIntegrationTrustProfile

[POS]
- app.core.integrations.catalog.trust_models
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class TrustTier(StrEnum):
    """Trust tier classification for catalog connectors and MCP servers."""

    OFFICIAL_VERIFIED = "OFFICIAL_VERIFIED"
    COMMUNITY_REVIEWED = "COMMUNITY_REVIEWED"
    UNREVIEWED = "UNREVIEWED"
    REVOKED = "REVOKED"


class ReviewStatus(StrEnum):
    """Security audit status of the catalog integration."""

    APPROVED = "APPROVED"
    PENDING_REVIEW = "PENDING_REVIEW"
    FLAGGED = "FLAGGED"
    REVOKED = "REVOKED"


class CapabilitySurface(BaseModel):
    """Declared capability surface exposing tool interfaces and permissions."""

    declared_tools: list[str] = Field(
        default_factory=list,
        description="List of declared MCP tool names exposed by this connector",
    )
    required_credentials: list[str] = Field(
        default_factory=list,
        description="Credential identifiers or environment variable keys needed",
    )
    requires_network_egress: bool = Field(
        default=False,
        description="Whether this connector initiates outbound network requests",
    )
    egress_destinations: list[str] = Field(
        default_factory=list,
        description="Target host domains reached by this connector",
    )


class LeastPrivilegeProposal(BaseModel):
    """Recommended minimum tool authorization subset for safest operation."""

    recommended_tools: list[str] = Field(
        default_factory=list,
        description="Narrowed list of tools recommended for initial whitelisting",
    )
    sensitive_tools_isolated: list[str] = Field(
        default_factory=list,
        description="High-privilege or destructive tools recommended to keep disabled initially",
    )
    rationale: str = Field(
        default="",
        description="Explanation for the recommended permission boundaries",
    )


class ProvenancePinning(BaseModel):
    """Source provenance and pinned artifact release identity."""

    publisher: str = Field(..., description="Entity or maintainer responsible for the server")
    repository_url: str | None = Field(default=None, description="Official upstream repository URL")
    pinned_version: str = Field(..., description="Immutable pinned version or commit hash")
    package_digest: str | None = Field(default=None, description="Cryptographic SHA-256 package digest")


class ReviewMetadata(BaseModel):
    """Audit review timeline and expiration attributes."""

    reviewer: str = Field(..., description="Auditing organization or agent")
    reviewed_at: float = Field(..., description="UNIX timestamp when audit was completed")
    review_expires_at: float = Field(..., description="UNIX timestamp when audit expires requiring re-review")
    status: ReviewStatus = Field(..., description="Current review status")
    notes: str | None = Field(default=None, description="Audit observations or constraints")


class CatalogTrustProfile(BaseModel):
    """Comprehensive trust profile associated with a catalog connector."""

    connector_id: str = Field(..., description="Unique connector ID matching CatalogEntry.id")
    trust_tier: TrustTier = Field(..., description="Assigned trust classification tier")
    review: ReviewMetadata = Field(..., description="Audit review details")
    capabilities: CapabilitySurface = Field(..., description="Declared tool and permission surface")
    least_privilege: LeastPrivilegeProposal = Field(..., description="Recommended initial authorization boundary")
    provenance: ProvenancePinning = Field(..., description="Source provenance and version pinning")
