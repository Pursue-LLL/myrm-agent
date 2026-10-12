"""Pydantic schemas for Security Audit Explicit Coverage & Replayable Repair Bundles.

[INPUT]
- None.

[OUTPUT]
- Typed DTO models for declared application models, explicit coverage scopes,
  challenged findings, replayable repair bundles, and full coverage reports.

[POS]
- Server schemas. Exposes typed contracts for client UI and security audit endpoints.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ApplicationModelDto(BaseModel):
    """Declared boundary model of the application under security audit."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., description="Target application or service name")
    tech_stack: list[str] = Field(..., description="Detected or declared tech stack items")
    entrypoints: list[str] = Field(..., description="Public routes and entrypoint endpoints")
    trust_boundaries: list[str] = Field(..., description="Perimeter and trust boundaries")
    data_flows: list[str] = Field(..., description="Critical data flow pipelines")
    supported_finding_categories: list[str] = Field(
        ..., description="Categories of findings supported by this model"
    )


class CoverageScopeItemDto(BaseModel):
    """Explicit disclosure of audit coverage depth for a specific security dimension."""

    model_config = ConfigDict(extra="forbid")

    category: str = Field(..., description="Coverage category, e.g. AUTH_ACCESS_CONTROL")
    status: str = Field(
        ..., description="Coverage status: COVERED, PARTIALLY_COVERED, UNCOVERED_UNSUPPORTED, etc."
    )
    audit_surface: str = Field(..., description="Description of the audited code/service surface")
    coverage_percentage: float = Field(..., description="Coverage percentage from 0.0 to 100.0")
    uncovered_reason: str | None = Field(
        default=None, description="Explicit rationale for uncovered or skipped scopes"
    )


class AuditFindingDto(BaseModel):
    """Confirmed security finding supported by the application model."""

    model_config = ConfigDict(extra="forbid")

    finding_id: str = Field(..., description="Unique finding identifier")
    category: str = Field(..., description="Finding category")
    severity: str = Field(..., description="Severity rating: CRITICAL, HIGH, MEDIUM, LOW, INFO")
    title: str = Field(..., description="Short finding summary title")
    description: str = Field(..., description="Detailed description of the issue")
    application_model_ref: str = Field(..., description="Reference to entrypoint or boundary in model")
    evidence: str = Field(..., description="Concrete code or trace evidence supporting finding")
    challenge_status: str = Field(
        default="UNCHALLENGED",
        description="Challenge status: UNCHALLENGED, CHALLENGED_CONFIRMED, CHALLENGED_REFUTED",
    )
    challenge_notes: str = Field(default="", description="Adversarial review challenge notes")
    verification_tier: str = Field(
        default="SELF_REPORTED",
        description="Honest evidence tier: SELF_REPORTED vs TESTED",
    )


class RepairPatchDto(BaseModel):
    """Atomic file diff patch within a replayable repair bundle."""

    model_config = ConfigDict(extra="forbid")

    file_path: str = Field(..., description="Relative file path targeted by patch")
    target_checksum: str = Field(..., description="Expected pre-patch file checksum")
    diff_content: str = Field(..., description="Unified diff patch content")
    replay_command: str = Field(..., description="Shell command to apply patch, e.g. git apply")


class ReplayableRepairBundleDto(BaseModel):
    """Self-contained verifiable bundle of patches and replay validation steps."""

    model_config = ConfigDict(extra="forbid")

    bundle_id: str = Field(..., description="Unique bundle identifier")
    finding_id: str = Field(..., description="Finding ID this bundle remediates")
    patches: list[RepairPatchDto] = Field(..., description="List of atomic repair patches")
    replay_script: str = Field(..., description="Replay validation command or script")
    checksum: str = Field(..., description="SHA-256 cryptographic binding checksum")
    is_verified: bool = Field(default=False, description="Whether bundle passed replay verification")


class ExplicitAuditCoverageReportDto(BaseModel):
    """Complete security audit report disclosing explicit coverage, findings, and repair bundles."""

    model_config = ConfigDict(extra="forbid")

    audit_id: str = Field(..., description="Unique audit run identifier")
    application_model: ApplicationModelDto = Field(..., description="Declared application model")
    scopes: list[CoverageScopeItemDto] = Field(..., description="Explicit coverage breakdown")
    findings: list[AuditFindingDto] = Field(..., description="Active confirmed findings")
    repair_bundles: list[ReplayableRepairBundleDto] = Field(
        ..., description="Associated replayable repair bundles"
    )
    overall_coverage_percentage: float = Field(
        ..., description="Average aggregate coverage percentage across all categories"
    )


class InitializeAuditSessionRequest(BaseModel):
    """Payload to initialize a new security audit session with an application model."""

    model_config = ConfigDict(extra="forbid")

    application_model: ApplicationModelDto = Field(..., description="Target application model")
    scopes: list[CoverageScopeItemDto] = Field(
        default_factory=list, description="Initial coverage scope disclosures"
    )


class RecordFindingRequest(BaseModel):
    """Payload to record and adversarially challenge a security finding."""

    model_config = ConfigDict(extra="forbid")

    finding: AuditFindingDto = Field(..., description="Finding to record")
    codebase_context: str = Field(
        default="", description="Relevant codebase context to check for mitigating controls"
    )
    auto_challenge: bool = Field(
        default=True, description="Whether to run independent adversarial challenge immediately"
    )


class AttachRepairBundleRequest(BaseModel):
    """Payload to generate and attach a replayable repair bundle to a finding."""

    model_config = ConfigDict(extra="forbid")

    finding_id: str = Field(..., description="Target finding ID")
    patches: list[RepairPatchDto] = Field(..., description="Repair patches")
    replay_script: str = Field(..., description="Replay test script")
    verify_immediately: bool = Field(
        default=True, description="Whether to verify checksum and replay immediately"
    )
