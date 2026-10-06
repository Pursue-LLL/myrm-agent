"""Pydantic schemas for Connector Catalog Trust Grading and Server Review Provenance.

[INPUT]
- None (Self-contained schema representations for connector trust requests and responses)

[OUTPUT]
- CatalogTrustProfileResponse, InstallationPreflightRequest, InstallationPreflightResponse, ContinuousReviewReportResponse, UnreviewedDisclosureResponse

[POS]
- app.schemas.connector_trust
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.core.integrations.catalog.trust_models import (
    CapabilitySurface,
    LeastPrivilegeProposal,
    ProvenancePinning,
    ReviewMetadata,
    TrustTier,
)


class CatalogTrustProfileResponse(BaseModel):
    """Trust classification, review metadata, and security profile of a connector."""

    connector_id: str = Field(..., description="Connector unique ID")
    trust_tier: TrustTier = Field(..., description="Assigned trust classification tier")
    review: ReviewMetadata = Field(..., description="Security audit review details")
    capabilities: CapabilitySurface = Field(..., description="Declared tool and permission surface")
    least_privilege: LeastPrivilegeProposal = Field(..., description="Recommended minimum authorization subset")
    provenance: ProvenancePinning = Field(..., description="Source provenance and version pinning")


class InstallationPreflightRequest(BaseModel):
    """Payload to perform pre-flight security evaluation before installing an MCP connector."""

    connector_id: str = Field(..., description="Target connector identifier to inspect")
    target_version: str | None = Field(
        default=None,
        description="Version string about to be installed (if omitted, pinned version is evaluated)",
    )


class InstallationPreflightResponse(BaseModel):
    """Security recommendation and disclosure returned prior to installation."""

    connector_id: str = Field(..., description="Target connector identifier")
    trust_tier: str = Field(..., description="Trust classification (OFFICIAL_VERIFIED, UNREVIEWED, etc.)")
    is_approved_for_install: bool = Field(..., description="Whether connector meets automated safety policy")
    requires_explicit_unreviewed_confirmation: bool = Field(
        ...,
        description="Whether user must manually click through unreviewed risk acknowledgement",
    )
    unreviewed_risk_disclosure: str | None = Field(
        default=None,
        description="Prominent risk disclosure text if integration is unreviewed",
    )
    recommended_tools: list[str] = Field(
        default_factory=list,
        description="Least-privilege initial tool whitelist recommended by security board",
    )
    sensitive_tools_isolated: list[str] = Field(
        default_factory=list,
        description="High-privilege or mutating tools that should remain disabled initially",
    )
    rationale: str = Field(default="", description="Least-privilege recommendation rationale")
    pinned_version: str = Field(..., description="Audited release version")
    has_provenance_drift: bool = Field(..., description="Whether version or source drift is detected")
    drift_warning: str | None = Field(default=None, description="Drift warning message if applicable")


class ContinuousReviewReportResponse(BaseModel):
    """Outcome of periodic continuous security audit and version drift inspection."""

    total_audited: int = Field(..., description="Count of evaluated active profiles")
    expired_revocations: list[str] = Field(
        default_factory=list,
        description="Connector IDs whose audits expired and were downgraded",
    )
    drift_alerts: list[str] = Field(
        default_factory=list,
        description="Connectors detected with unauthorized version or provenance drift",
    )
    audit_timestamp: float = Field(..., description="Timestamp when continuous review was run")


class UnreviewedDisclosureResponse(BaseModel):
    """Honest disclosure text and legal disclaimer for unreviewed connectors."""

    connector_id: str = Field(..., description="Target connector identifier")
    disclosure_text: str = Field(..., description="Honest risk and liability disclosure")
    risk_acknowledgement_required: bool = Field(
        default=True,
        description="Requires user explicit confirmation checkbox in UI before connecting",
    )
