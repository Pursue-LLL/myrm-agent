"""
[POS] app/schemas/vnc_hardening.py
[INPUT] pydantic
[OUTPUT] VNC loopback bind and rfbauth hardening request and response DTOs
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class VncSecurityAuditViolationDTO(BaseModel):
    """Structured security audit violation detected in VNC configuration or flags."""

    violation_type: str = Field(..., description="Classification of security violation")
    description: str = Field(..., description="Human-readable rationale and threat explanation")
    flag_or_path: str = Field(..., description="Conflicting command line flag, parameter, or filepath")
    auto_remediated: bool = Field(default=False, description="Whether this violation was automatically sanitized")


class SanitizeVncLaunchConfigRequestDTO(BaseModel):
    """Payload to sanitize x11vnc launch configuration."""

    display_num: int = Field(default=0, ge=0, description="X11 display number, e.g. 0 for :0")
    vnc_port: int = Field(default=5900, ge=1024, le=65535, description="Native RFB listening port")
    passwd_file: str = Field(..., min_length=1, description="Path to rfbauth encrypted password file")
    bind_mode: str = Field(default="loopback", description="Intended network bind mode: loopback or non_loopback_opt_in")
    non_loopback_opt_in: bool = Field(
        default=False,
        description="Explicit administrator opt-in flag required for non-loopback exposure",
    )
    opt_in_password: str | None = Field(
        default=None,
        description="Password required when requesting explicit non-loopback bind",
    )
    extra_flags: list[str] = Field(default_factory=list, description="Additional x11vnc command line flags")
    auto_remediate: bool = Field(default=True, description="Whether to automatically sanitize conflicting flags")


class VncHardenedLaunchSpecDTO(BaseModel):
    """Sanitized, hardened command line specification for x11vnc."""

    command_args: list[str] = Field(..., description="Final hardened command line tokens for exec")
    effective_bind_mode: str = Field(..., description="Enforced effective binding mode: loopback or non_loopback_opt_in")
    rfbauth_path: str = Field(..., description="Enforced rfbauth credential file path")
    violations: list[VncSecurityAuditViolationDTO] = Field(
        default_factory=list,
        description="Security violations detected and remediated during sanitization",
    )
    is_hardened: bool = Field(default=True, description="Whether spec complies with zero-trust baseline")


class AuditRawVncCommandRequestDTO(BaseModel):
    """Payload to audit an existing raw x11vnc command line argument list."""

    command_args: list[str] = Field(..., description="Raw command line argument list to evaluate")


class VncHardeningAuditReportDTO(BaseModel):
    """Audit report evaluating compliance of an x11vnc invocation."""

    timestamp: float = Field(..., description="Evaluation epoch timestamp")
    spec: VncHardenedLaunchSpecDTO = Field(..., description="Evaluated hardened launch specification")
    verdict: str = Field(..., description="Audit verdict: PASS or BLOCKED")
    remediation_summary: list[str] = Field(
        default_factory=list,
        description="Summary of auto-remediation steps applied to secure the instance",
    )


class GenerateSecurePasswordRequestDTO(BaseModel):
    """Payload to request high-entropy VNC password generation."""

    length: int = Field(default=14, ge=8, le=64, description="Desired password length")


class GenerateSecurePasswordResponseDTO(BaseModel):
    """Generated secure VNC password."""

    password: str = Field(..., description="High-entropy generated password")
    meets_policy: bool = Field(default=True, description="Whether generated password meets security baseline")


class EvaluatePasswordRequestDTO(BaseModel):
    """Payload to evaluate password strength against policy."""

    password: str = Field(..., min_length=1, description="Password to evaluate")


class EvaluatePasswordResponseDTO(BaseModel):
    """Password strength policy evaluation result."""

    is_valid: bool = Field(..., description="Whether password satisfies strength requirements")
    reason: str = Field(..., description="Validation summary or rejection reason")
