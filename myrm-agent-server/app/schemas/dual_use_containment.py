"""
[POS] app/schemas/dual_use_containment.py
[INPUT] pydantic
[OUTPUT] MitreAttackTacticEnum, SkillSensitivityLevelEnum, ArtifactSecurityClassificationEnum, EgressDestinationTrustEnum, SkillTtpEvaluationRequest, SkillTtpEvaluationResponse, ExecutionGateCheckRequest, ExecutionGateCheckResponse, ArtifactEgressEvaluationRequest, ArtifactEgressEvaluationResponse, FlightRecorderEntrySchema, DualUseMetricsResponse

Pydantic schemas for dual-use skill containment and artifact exfiltration shield suite.

Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class MitreAttackTacticEnum(StrEnum):
    """MITRE ATT&CK tactic classifications."""

    INITIAL_ACCESS = "initial_access"
    EXECUTION = "execution"
    PERSISTENCE = "persistence"
    PRIVILEGE_ESCALATION = "privilege_escalation"
    CREDENTIAL_ACCESS = "credential_access"
    DISCOVERY = "discovery"
    LATERAL_MOVEMENT = "lateral_movement"
    COMMAND_AND_CONTROL = "command_and_control"
    EXFILTRATION = "exfiltration"
    IMPACT = "impact"


class SkillSensitivityLevelEnum(StrEnum):
    """Skill sensitivity level enumeration."""

    BENIGN = "benign"
    DUAL_USE_SENSITIVE = "dual_use_sensitive"
    MALICIOUS_PROHIBITED = "malicious_prohibited"


class ArtifactSecurityClassificationEnum(StrEnum):
    """Artifact classification level."""

    PUBLIC = "public"
    INTERNAL = "internal"
    RESTRICTED_ARTIFACT = "restricted_artifact"


class EgressDestinationTrustEnum(StrEnum):
    """Trust classification of the outbound destination."""

    ALLOWLISTED_INTERNAL = "allowlisted_internal"
    AUTHORIZED_PRIVATE_REPO = "authorized_private_repo"
    UNTRUSTED_PUBLIC_EXTERNAL = "untrusted_public_external"


class SkillTtpEvaluationRequest(BaseModel):
    """Request payload to analyze skill TTPs."""

    skill_name: str = Field(..., min_length=1, max_length=100, description="Skill identifier.")
    description: str = Field(default="", description="Skill description or task overview.")
    command_signatures: list[str] = Field(default_factory=list, description="Associated command line patterns.")


class SkillTtpEvaluationResponse(BaseModel):
    """Response payload detailing TTP classification."""

    skill_name: str = Field(..., description="Evaluated skill name.")
    tactics: list[MitreAttackTacticEnum] = Field(..., description="Matched MITRE ATT&CK tactics.")
    sensitivity_level: SkillSensitivityLevelEnum = Field(..., description="Sensitivity classification.")
    requires_hitl_approval: bool = Field(..., description="Whether human approval is required.")
    quarantine_pod_enforced: bool = Field(..., description="Whether execution must be isolated in pod.")
    identified_signatures: list[str] = Field(default_factory=list, description="Identified threat signatures.")


class ExecutionGateCheckRequest(BaseModel):
    """Request payload to verify dual-use skill execution authorization."""

    skill_name: str = Field(..., min_length=1, max_length=100, description="Skill name.")
    command_line: str = Field(..., description="Specific command line to execute.")
    target_host_or_ip: str = Field(..., description="Target host or IP address.")
    approval_token: str = Field(default="", description="Pre-issued human approval token.")
    is_running_in_quarantine_pod: bool = Field(default=False, description="Whether currently in quarantine pod.")


class ExecutionGateCheckResponse(BaseModel):
    """Response payload determining if skill execution is permitted."""

    permitted: bool = Field(..., description="Whether execution is authorized.")
    requires_hitl_modal: bool = Field(..., description="Whether human confirmation modal must be displayed.")
    sensitivity_level: SkillSensitivityLevelEnum = Field(..., description="Assigned sensitivity level.")
    enforce_quarantine_pod: bool = Field(..., description="Whether quarantine pod is mandatory.")
    reason: str = Field(default="", description="Authorization or rejection justification.")
    matched_tactics: list[MitreAttackTacticEnum] = Field(default_factory=list, description="Matched tactics.")
    hitl_prompt_warning: str = Field(default="", description="Warning prompt for human operator modal.")


class ArtifactEgressEvaluationRequest(BaseModel):
    """Request payload to inspect outbound artifact transmission."""

    artifact_id: str = Field(..., min_length=1, max_length=128, description="Artifact ID.")
    artifact_name: str = Field(..., min_length=1, max_length=256, description="Artifact filename.")
    content_base64: str = Field(default="", description="Base64-encoded artifact content or empty for test.")
    target_destination: str = Field(..., description="Target URL, repo, or endpoint.")
    explicit_classification: ArtifactSecurityClassificationEnum | None = Field(
        default=None, description="Optional manual override classification."
    )


class ArtifactEgressEvaluationResponse(BaseModel):
    """Response payload detailing exfiltration inspection outcome."""

    artifact_id: str = Field(..., description="Artifact ID.")
    artifact_name: str = Field(..., description="Artifact filename.")
    classification: ArtifactSecurityClassificationEnum = Field(..., description="Assigned classification.")
    target_destination: str = Field(..., description="Destination target.")
    destination_trust: EgressDestinationTrustEnum = Field(..., description="Destination trust evaluation.")
    is_blocked: bool = Field(..., description="Whether outbound transmission is blocked.")
    violation_reason: str = Field(default="", description="Reason for block if exfiltration prevented.")
    sha256_hash: str = Field(default="", description="SHA-256 fingerprint of artifact.")
    evaluated_at: str = Field(default="", description="Evaluation ISO timestamp.")


class FlightRecorderEntrySchema(BaseModel):
    """Audit entry from flight recorder."""

    entry_id: str = Field(..., description="Unique event identifier.")
    event_type: str = Field(..., description="Type of event.")
    subject: str = Field(..., description="Evaluated subject (skill or artifact).")
    decision: str = Field(..., description="Recorded decision.")
    details: dict[str, str | int | float | bool] = Field(default_factory=dict, description="Event context.")
    timestamp: str = Field(..., description="ISO timestamp.")


class DualUseMetricsResponse(BaseModel):
    """Operational telemetry and mitigation metrics."""

    total_skill_evaluations: int = Field(..., ge=0, description="Total skill evaluations performed.")
    dual_use_skills_detected: int = Field(..., ge=0, description="Total dual-use sensitive skills found.")
    hitl_approvals_requested: int = Field(..., ge=0, description="Total HITL approval modals requested.")
    host_execution_blocks: int = Field(..., ge=0, description="Total executions blocked due to host isolation.")
    total_artifact_scans: int = Field(..., ge=0, description="Total outbound artifact scans.")
    exfiltration_blocks: int = Field(..., ge=0, description="Total blocked exfiltration attempts.")
