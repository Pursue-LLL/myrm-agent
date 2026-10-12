"""Pydantic schemas for Executable Capability Probing.

[INPUT]
- None.

[OUTPUT]
- Typed DTO models for diagnosing executable readiness and compatibility.

[POS]
- Server schemas for Claude-Mem #4167 shell-immune executable probing.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class ExecutableProbeStatusDto(StrEnum):
    """Tri-state classification for CLI/executable health and compatibility."""

    CAPABLE = "capable"
    INCOMPATIBLE = "incompatible"
    BROKEN = "broken"


class ProbeExecutableRequest(BaseModel):
    """Request payload for probing an executable candidate."""

    model_config = ConfigDict(extra="forbid")

    candidate_path: str = Field(
        ..., description="Absolute path or executable name to test"
    )
    capability_flags: list[str] = Field(
        default_factory=lambda: ["--version"],
        description="Flags required to confirm full compatibility",
    )
    version_flag: str = Field(
        default="--version", description="Baseline flag to test if binary spawns"
    )
    timeout_sec: float = Field(
        default=5.0, ge=0.5, le=60.0, description="Process execution timeout"
    )
    warm_up_retry: bool = Field(
        default=True, description="Whether to retry capability probe after version test"
    )


class ProbeExecutableResponse(BaseModel):
    """Response payload containing diagnostic outcome."""

    model_config = ConfigDict(extra="forbid")

    candidate_path: str
    status: ExecutableProbeStatusDto
    version: str | None = None
    detail: str
    launch_failed: bool
    is_capable: bool
