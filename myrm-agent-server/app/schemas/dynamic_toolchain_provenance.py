"""
[POS] app/schemas/dynamic_toolchain_provenance.py
[INPUT] pydantic
[OUTPUT] SkillProvenanceManifestSchema, ASTScanFindingResponse, SandboxConfinementPolicyResponse, ToolchainVerificationDecisionResponse, EvaluateAndInstallSkillRequest, VerifyProvenanceOnlyRequest, VerifyProvenanceOnlyResponse, ScanASTOnlyRequest, ScanASTOnlyResponse, ManagePublisherRequest, CheckPermissionRequest, CheckPermissionResponse, DynamicToolchainMetricsResponse

Pydantic schemas for Dynamic Toolchain Supply Chain Provenance & Pre-Install Sandbox Hardening.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class SkillProvenanceManifestSchema(BaseModel):
    """Declared cryptographic provenance metadata of a dynamic toolchain skill."""

    skill_id: str = Field(..., description="Unique skill identifier")
    version: str = Field(..., description="Semver version string")
    publisher_id: str = Field(..., description="Identity of publisher or registry maintainer")
    source_sha256: str = Field(..., description="Declared hex SHA-256 digest of source bundle")
    signature: str = Field(..., description="Cryptographic publisher signature")
    declared_domains: list[str] = Field(default_factory=list, description="Allowed outbound network domains")
    declared_paths: list[str] = Field(default_factory=list, description="Allowed filesystem read/write paths")
    declared_env_keys: list[str] = Field(default_factory=list, description="Allowed environment variables")


class ASTScanFindingResponse(BaseModel):
    """Details of a static code violation found by AST scan."""

    violation_type: str = Field(..., description="Category of AST violation")
    symbol_name: str = Field(..., description="Discovered forbidden symbol or function")
    line_number: int = Field(..., description="Source code line number")
    detail: str = Field(..., description="Diagnostic explanation")


class SandboxConfinementPolicyResponse(BaseModel):
    """JIT least-privilege sandbox confinement profile for an installed skill."""

    policy_id: str = Field(..., description="Unique policy identifier")
    skill_id: str = Field(..., description="Target skill ID")
    allowed_domains: list[str] = Field(..., description="Sanitized outbound network domains")
    allowed_paths: list[str] = Field(..., description="Sanitized filesystem paths")
    allowed_env_keys: list[str] = Field(..., description="Sanitized environment variables")
    is_confined: bool = Field(..., description="Confinement active state")
    created_at: float = Field(..., description="Unix timestamp of policy issuance")


class ToolchainVerificationDecisionResponse(BaseModel):
    """Comprehensive decision payload for skill verification and sandbox installation."""

    skill_id: str = Field(..., description="Skill ID")
    provenance_status: str = Field(..., description="Cryptographic provenance status code")
    is_provenance_valid: bool = Field(..., description="Whether provenance passed verification")
    ast_findings: list[ASTScanFindingResponse] = Field(..., description="Detected AST violations")
    is_ast_clean: bool = Field(..., description="Whether AST scan found zero violations")
    is_installation_approved: bool = Field(..., description="Overall approval for sandbox mounting")
    confinement_policy: SandboxConfinementPolicyResponse | None = Field(
        default=None,
        description="Issued sandbox confinement policy if approved",
    )
    explanation: str = Field(..., description="Detailed decision explanation")
    timestamp: float = Field(..., description="Unix timestamp of decision")


class EvaluateAndInstallSkillRequest(BaseModel):
    """Request payload to vet and install a dynamic skill."""

    source_code: str = Field(..., description="Python source code of the extension")
    manifest: SkillProvenanceManifestSchema = Field(..., description="Cryptographic provenance metadata")


class VerifyProvenanceOnlyRequest(BaseModel):
    """Request payload to verify provenance without AST scan or installation."""

    source_code: str = Field(..., description="Source code to verify")
    manifest: SkillProvenanceManifestSchema = Field(..., description="Declared provenance manifest")


class VerifyProvenanceOnlyResponse(BaseModel):
    """Outcome of standalone provenance verification."""

    provenance_status: str = Field(..., description="Verification status code")
    explanation: str = Field(..., description="Verification explanation")


class ScanASTOnlyRequest(BaseModel):
    """Request payload to run standalone AST static analysis."""

    source_code: str = Field(..., description="Python source code to scan")
    skill_id: str = Field(default="", description="Optional skill identifier for logging")


class ScanASTOnlyResponse(BaseModel):
    """Outcome of standalone AST static scan."""

    skill_id: str = Field(..., description="Target skill ID")
    findings: list[ASTScanFindingResponse] = Field(..., description="List of detected AST violations")
    is_clean: bool = Field(..., description="True if zero violations were detected")


class ManagePublisherRequest(BaseModel):
    """Payload to register or revoke trusted publisher identity."""

    publisher_id: str = Field(..., description="Publisher identifier")


class CheckPermissionRequest(BaseModel):
    """Payload to evaluate if a target resource is allowed by a confinement policy."""

    policy: SandboxConfinementPolicyResponse = Field(..., description="Confinement policy")
    target_type: str = Field(..., description="Target type: 'network' | 'path' | 'env'")
    target_value: str = Field(..., description="Requested network domain, file path, or env key")


class CheckPermissionResponse(BaseModel):
    """Outcome of sandbox confinement permission check."""

    permitted: bool = Field(..., description="Whether requested operation is permitted")
    target_type: str = Field(..., description="Evaluated target type")
    target_value: str = Field(..., description="Evaluated target value")


class DynamicToolchainMetricsResponse(BaseModel):
    """Cumulative operational metrics for dynamic toolchain supply chain defense."""

    provenance_checks_total: int
    provenance_verified_total: int
    provenance_rejected_total: int
    ast_scans_total: int
    ast_violations_detected_total: int
    confinements_issued_total: int
    installations_approved_total: int
    installations_blocked_total: int
