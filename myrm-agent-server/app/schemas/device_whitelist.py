"""Pydantic schemas for Sandbox Container Device Whitelist Hardening
and Block Device Strip Suite.

[INPUT]
- pydantic BaseModel, ConfigDict, Field

[OUTPUT]
- VirtualDeviceSpecSchema: schema describing an authorized virtual pseudo-device
- DeviceInspectRequest: request payload to inspect a single device path
- DeviceInspectResponse: safety verdict and rule attribution for inspected device
- DeviceSanitizeRequest: request payload containing candidate device paths
- DeviceSanitizeResponse: audit report of allowed vs stripped devices
- CgroupRulesResponse: generated cgroup device permission rules and Docker args
- DevicePolicyConfigRequest: payload to update device policy
- DevicePolicyConfigResponse: current device policy settings

[POS]
Data contract for container device whitelist and block device stripping REST endpoints.
Strictly avoids Any types; enforced under 400 lines limit.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class VirtualDeviceSpecSchema(BaseModel):
    """Schema representing an authorized virtual pseudo-device node."""

    model_config = ConfigDict(extra="forbid")

    path: str = Field(..., description="Device path (e.g. '/dev/null')")
    major: int = Field(..., description="Major device number")
    minor: int = Field(..., description="Minor device number")
    device_type: str = Field(..., description="Device classification: 'c' or 'b'")
    permissions: str = Field(..., description="Access permissions: 'rwm'")
    description: str = Field(..., description="Human-readable description")


class DeviceInspectRequest(BaseModel):
    """Request payload to inspect a candidate device node."""

    model_config = ConfigDict(extra="forbid")

    device_path: str = Field(..., description="Device node path (e.g. '/dev/null', '/dev/sda')")


class DeviceInspectResponse(BaseModel):
    """Verdict on a candidate device node."""

    model_config = ConfigDict(extra="forbid")

    path: str = Field(..., description="Normalized device path")
    action: str = Field(..., description="Enforcement action: ALLOW or STRIP")
    device_type: str | None = Field(None, description="Device classification ('c' or 'b') if known")
    matched_rule: str = Field(..., description="Security rule matched")
    reason: str = Field(..., description="Detailed explanation of decision")


class DeviceSanitizeRequest(BaseModel):
    """Request payload to sanitize a list of container device nodes."""

    model_config = ConfigDict(extra="forbid")

    devices: list[str] = Field(..., description="List of device paths to sanitize before container startup")


class DeviceSanitizeResponse(BaseModel):
    """Sanitization audit report for container device nodes."""

    model_config = ConfigDict(extra="forbid")

    total_inspected: int = Field(..., description="Total device candidates evaluated")
    allowed_devices: list[str] = Field(..., description="List of safe authorized devices retained")
    stripped_devices: list[str] = Field(..., description="List of physical block or host devices stripped")
    reasons: list[str] = Field(..., description="Attribution reasons for stripped devices")
    is_fully_compliant: bool = Field(..., description="True if no dangerous devices were found")


class CgroupRulesResponse(BaseModel):
    """Generated cgroup isolation rules and docker arguments."""

    model_config = ConfigDict(extra="forbid")

    cgroup_rules: list[str] = Field(..., description="List of OCI/cgroup device whitelist rules")
    docker_device_args: list[str] = Field(..., description="Hardened Docker CLI command flags")


class DevicePolicyConfigRequest(BaseModel):
    """Payload to update container device policy settings."""

    model_config = ConfigDict(extra="forbid")

    strict_minimal_allowlist: bool = Field(
        default=True,
        description="Whether to restrict strictly to minimal virtual pseudo-devices",
    )
    strip_block_devices: bool = Field(
        default=True,
        description="Whether to strip all physical block devices (/dev/sd*, /dev/nvme*, etc.)",
    )
    strip_host_hardware_devices: bool = Field(
        default=True,
        description="Whether to strip host hardware nodes (/dev/mem, /dev/dri*, etc.)",
    )
    custom_allowed_devices: list[str] = Field(
        default_factory=list,
        description="Additional custom device paths explicitly permitted",
    )


class DevicePolicyConfigResponse(BaseModel):
    """Current container device policy configuration."""

    model_config = ConfigDict(extra="forbid")

    strict_minimal_allowlist: bool = Field(..., description="Strict minimal allowlist flag")
    strip_block_devices: bool = Field(..., description="Block device stripping flag")
    strip_host_hardware_devices: bool = Field(..., description="Host hardware stripping flag")
    custom_allowed_devices: list[str] = Field(..., description="Custom permitted devices")
