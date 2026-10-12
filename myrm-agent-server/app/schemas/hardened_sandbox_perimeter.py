"""
[POS] app/schemas/hardened_sandbox_perimeter.py
[INPUT] pydantic, enum
[OUTPUT] HardenedSandboxSpecRequest, RuntimeSpecValidationResponse, EgressEvaluateRequest, EgressEvaluateResponse, CredentialTicketMintRequest, CredentialTicketMintResponse, CredentialTicketVerifyRequest, CredentialTicketVerifyResponse, ProcessUsageEvaluateRequest, ProcessUsageEvaluateResponse, SandboxSafetyMetricsResponse

Pydantic schemas for Scale-Ready Hardened Agent Sandbox & Safety Perimeter Suite.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class SandboxIsolationModeEnum(StrEnum):
    """Underlying sandboxing isolation technology."""

    CONTAINER = "CONTAINER"
    MICRO_VM = "MICRO_VM"
    PROCESS_JAIL = "PROCESS_JAIL"


class EgressVerdictEnum(StrEnum):
    """Decision verdict for outbound network traffic."""

    ALLOWED = "ALLOWED"
    BLOCKED_PRIVATE_IP = "BLOCKED_PRIVATE_IP"
    BLOCKED_CLOUD_METADATA = "BLOCKED_CLOUD_METADATA"
    BLOCKED_DOMAIN_NOT_ALLOWLISTED = "BLOCKED_DOMAIN_NOT_ALLOWLISTED"
    BLOCKED_INVALID_HOST = "BLOCKED_INVALID_HOST"


class RuntimeSpecValidationVerdictEnum(StrEnum):
    """Decision verdict for sandbox startup parameter hardening."""

    VALID = "VALID"
    INVALID_ROOT_USER = "INVALID_ROOT_USER"
    INVALID_WRITABLE_ROOTFS = "INVALID_WRITABLE_ROOTFS"
    INVALID_MISSING_TMPFS_NOEXEC = "INVALID_MISSING_TMPFS_NOEXEC"
    INVALID_NO_PERSISTENT_VOLUME = "INVALID_NO_PERSISTENT_VOLUME"
    INVALID_RESOURCE_BOUNDS = "INVALID_RESOURCE_BOUNDS"


class HardenedSandboxSpecRequest(BaseModel):
    """Operational parameters for a proposed hardened sandbox container or microVM."""

    isolation_mode: SandboxIsolationModeEnum = Field(
        default=SandboxIsolationModeEnum.CONTAINER,
        description="Isolation architecture (CONTAINER, MICRO_VM, PROCESS_JAIL)",
    )
    is_non_root: bool = Field(default=True, description="Strict non-root execution flag")
    uid: int = Field(default=1000, ge=0, description="Host-mapped non-root User ID")
    gid: int = Field(default=1000, ge=0, description="Host-mapped non-root Group ID")
    read_only_rootfs: bool = Field(default=True, description="Enforce read-only root filesystem")
    tmpfs_noexec: bool = True
    persistent_volume_path: str = Field(
        default="/workspace", min_length=1, max_length=256, description="Mount point for dedicated persistent storage"
    )
    memory_limit_mb: int = Field(default=512, ge=64, le=32768, description="Memory limit in megabytes")
    cpu_quota_pct: float = Field(default=1.0, ge=0.1, le=64.0, description="CPU quota allocation")
    pids_max: int = Field(default=128, ge=10, le=2048, description="Maximum concurrent active processes")


class RuntimeSpecValidationResponse(BaseModel):
    """Evaluation result of sandbox runtime hardening."""

    is_valid: bool = Field(..., description="True if spec satisfies all hardening standards")
    verdict: RuntimeSpecValidationVerdictEnum = Field(..., description="Validation outcome code")
    violations: list[str] = Field(default_factory=list, description="Specific safety violations encountered")


class EgressEvaluateRequest(BaseModel):
    """Payload to evaluate an outbound network connection attempt."""

    host: str = Field(..., min_length=1, max_length=256, description="Target hostname or IP address")
    port: int = Field(default=443, ge=1, le=65535, description="Target destination port")
    scheme: str = Field(default="https", max_length=16, description="Protocol scheme")
    allowlisted_domains: list[str] | None = Field(
        default=None, description="Optional domain whitelist to enforce strictly"
    )


class EgressEvaluateResponse(BaseModel):
    """Result of outbound connection security evaluation."""

    is_allowed: bool = Field(..., description="True if connection passes SSRF and zero-trust checks")
    verdict: EgressVerdictEnum = Field(..., description="Egress decision verdict")
    reason: str = Field(..., description="Human-readable decision explanation")
    resolved_ip: str | None = Field(default=None, description="Resolved IP address")


class CredentialTicketMintRequest(BaseModel):
    """Payload to request an ephemeral capability ticket from host broker."""

    secret_alias: str = Field(..., min_length=1, max_length=128, description="Identifier of the master secret")
    allowed_scopes: list[str] = Field(default_factory=list, description="Authorized execution scopes")
    ttl_seconds: float = Field(default=300.0, ge=10.0, le=3600.0, description="Ticket time-to-live in seconds")


class CredentialTicketMintResponse(BaseModel):
    """Short-lived authorization ticket issued to the agent sandbox."""

    ticket_id: str = Field(..., description="Unique ticket identifier")
    secret_alias: str = Field(..., description="Secret identifier")
    ephemeral_token: str = Field(..., description="Scoped ephemeral access token")
    expires_at: float = Field(..., description="Epoch timestamp of expiration")
    allowed_scopes: list[str] = Field(..., description="Authorized capabilities")


class CredentialTicketVerifyRequest(BaseModel):
    """Payload to verify an ephemeral ticket."""

    ticket_id: str = Field(..., min_length=1, description="Ticket ID to verify")
    required_scope: str | None = Field(default=None, description="Specific scope to check")


class CredentialTicketVerifyResponse(BaseModel):
    """Ticket validation outcome."""

    is_valid: bool = Field(..., description="True if ticket is active, unexpired, and authorized")
    ticket_id: str = Field(..., description="Verified ticket ID")


class ProcessUsageEvaluateRequest(BaseModel):
    """Payload containing runtime process telemetry sampled from the sandbox."""

    agent_id: str = Field(..., min_length=1, max_length=128, description="Executing agent ID")
    active_pids_count: int = Field(..., ge=0, description="Current number of active processes")
    memory_used_mb: float = Field(..., ge=0.0, description="Current resident memory consumed")
    cpu_percent: float = Field(default=0.0, ge=0.0, description="Current CPU utilization")
    pids_max: int = Field(default=128, ge=10, description="Process ceiling threshold")
    memory_limit_mb: float = Field(default=512.0, ge=64.0, description="Memory limit threshold")


class ProcessUsageEvaluateResponse(BaseModel):
    """Process hierarchy and resource security verdict."""

    is_safe: bool = Field(..., description="True if process metrics are within safe bounds")
    agent_id: str = Field(..., description="Agent ID")
    message: str = Field(..., description="Status summary or fork-bomb detection reason")
    is_circuit_broken: bool = Field(..., description="True if sandbox process guard is tripped")


class SandboxSafetyMetricsResponse(BaseModel):
    """Cumulative operational metrics for hardened sandbox perimeter defenses."""

    total_spec_validations: int = Field(..., ge=0)
    spec_validation_failures: int = Field(..., ge=0)
    egress_requests_evaluated: int = Field(..., ge=0)
    ssrf_blocks: int = Field(..., ge=0)
    credential_tickets_minted: int = Field(..., ge=0)
    fork_bomb_mitigations: int = Field(..., ge=0)
