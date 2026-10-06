"""Pydantic schemas for Docker Sandbox 8-Flag Physical Hardening and Vault-Proxy Suite.

[INPUT]
None (Pydantic schema definitions).

[OUTPUT]
NetworkIsolationEnum, ProvisionStatusEnum: Enums for network and lifecycle status.
EightFlagConfigRequest: Configuration matrix for physical hardening flags.
SecretVaultConfig: Config for secret injection and masking.
HardenedSandboxResponse: Status response DTO.

[POS]
Docker 沙箱物理加固与 Vault-Proxy 凭证代理模式层。定义 8 标志物理隔离矩阵、只读文件系统、无执行挂载与网络气隙数据契约。
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class NetworkIsolationEnum(StrEnum):
    """Network isolation modes."""

    NONE = "none"
    HOST = "host"
    BRIDGE_RESTRICTED = "bridge_restricted"


class ProvisionStatusEnum(StrEnum):
    """Sandbox provision lifecycle status."""

    UNINITIALIZED = "uninitialized"
    WARM = "warm"
    RUNNING = "running"
    DISPOSED = "disposed"


class EightFlagConfigRequest(BaseModel):
    """Configuration matrix for 8 physical hardening flags."""

    read_only: bool = Field(default=True, description="Enforce read-only rootfs")
    tmp_size_mb: int = Field(default=100, ge=1, le=2048, description="RAM tmpfs size in MB")
    tmp_noexec: bool = Field(default=True, description="Enforce noexec on /tmp")
    pids_limit: int = Field(default=100, ge=10, le=2000, description="Max process tree limit")
    cap_drop_all: bool = Field(default=True, description="Drop all Linux capabilities")
    no_new_privileges: bool = Field(default=True, description="Prevent setuid escalation")
    user: str = Field(default="1000:1000", description="Non-root unprivileged UID:GID")
    network_mode: NetworkIsolationEnum = Field(
        default=NetworkIsolationEnum.NONE, description="Physical air-gap network mode"
    )
    memory_limit: str = Field(default="512m", description="RAM limit boundary")
    cpus_quota: float = Field(default=1.0, gt=0.0, le=64.0, description="CPU core quota")
    auto_remove: bool = Field(default=True, description="Container auto-remove flag (--rm)")


class BuildRunArgsRequest(BaseModel):
    """Request payload to construct hardened Docker arguments."""

    image: str = Field(..., description="Target Docker image")
    command: list[str] | None = Field(default=None, description="Command to execute")
    extra_mounts: list[str] | None = Field(default=None, description="Host volume mounts")
    config: EightFlagConfigRequest | None = Field(default=None, description="Custom 8-flag config")


class HardenedDockerCommandResponse(BaseModel):
    """Response containing assembled Docker run arguments and verification."""

    raw_args: list[str]
    flags_verified: bool
    missing_flags: list[str]


class VerifyFlagsRequest(BaseModel):
    """Request payload to verify arbitrary Docker command flags."""

    raw_args: list[str] = Field(..., description="List of command arguments to audit")


class VerifyFlagsResponse(BaseModel):
    """Audit outcome of 8-flag presence."""

    flags_verified: bool
    missing_flags: list[str]


class CheckEnvLeakRequest(BaseModel):
    """Request payload to audit environment arguments for plaintext credentials."""

    env_args: list[str] = Field(..., description="Arguments containing environment parameters")


class CheckEnvLeakResponse(BaseModel):
    """Outcome of plaintext environment leakage audit."""

    is_safe: bool
    detected_leaks: list[str]


class RegisterVaultCredentialRequest(BaseModel):
    """Request payload to register a sensitive token in host vault."""

    credential_id: str = Field(..., description="Unique credential key identifier")
    target_service: str = Field(..., description="Target service name (e.g. GitHub API)")
    secret_value: str = Field(..., min_length=1, description="Actual sensitive token/key")
    allowed_domains: list[str] = Field(..., min_length=1, description="Domain allowlist")
    description: str = Field(default="", description="Optional human-readable description")


class VaultCredentialMetadataResponse(BaseModel):
    """Response containing redacted vault credential entry."""

    credential_id: str
    target_service: str
    secret_value: str = Field(default="[REDACTED_IN_VAULT]")
    allowed_domains: list[str]
    description: str


class VaultProxyRelayRequest(BaseModel):
    """Request sent from sandbox through host proxy with placeholder."""

    project_id: str
    target_url: str
    method: str = Field(default="GET")
    credential_id: str
    headers: dict[str, str] = Field(default_factory=dict)
    body: str = Field(default="")


class VaultProxyRelayResponse(BaseModel):
    """Response returned through host vault proxy."""

    status_code: int
    headers: dict[str, str]
    body: str
    credential_injected: bool
    blocked_reason: str | None


class LazyProvisionResponse(BaseModel):
    """Response from on-demand sandbox provisioning."""

    container_id: str | None
    status: ProvisionStatusEnum
    flags_verified: bool
    command_spec: list[str] | None
