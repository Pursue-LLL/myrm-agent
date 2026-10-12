"""Pydantic schemas for Redirect Private Address Hop Revalidation Suite.

[INPUT]
- pydantic BaseModel, Field

[OUTPUT]
- HopEvaluationRequest: request payload for evaluating a network hop URL
- HopEvaluationResponse: result of hop safety evaluation
- HopPolicyConfigRequest: update payload for hop guard policy
- HopPolicyConfigResponse: current policy settings
- HopViolationRecordResponse: single audit record of blocked hop
- HopViolationsListResponse: collection of violation records
- HopSimulationRequest: payload to simulate and record a hop violation

[POS]
Data contract for redirect hop revalidation REST endpoints.
Strictly avoids Any types; enforced under 400 lines limit.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class HopEvaluationRequest(BaseModel):
    """Payload to evaluate a URL for hop-by-hop private network risks."""

    model_config = ConfigDict(extra="forbid")

    target_url: str = Field(..., description="Target URL being redirected to or requested")
    resource_type: str = Field(
        default="document",
        description="Resource type (e.g., 'document', 'fetch', 'xhr', 'script', 'image')",
    )


class HopEvaluationResponse(BaseModel):
    """Result of evaluating a network hop URL."""

    model_config = ConfigDict(extra="forbid")

    disposition: str = Field(..., description="Action taken: ALLOW, ABORT_SUBRESOURCE, or ABORT_AND_RESET_DOCUMENT")
    is_private: bool = Field(..., description="Whether target is detected as private, loopback, or metadata")
    matched_rule: str = Field(..., description="Matched security rule identifier")
    target_url: str = Field(..., description="Evaluated destination URL")
    resource_type: str = Field(..., description="Request resource type")
    reason: str = Field(..., description="Explanation of evaluation decision")


class HopPolicyConfigRequest(BaseModel):
    """Payload to update the redirect hop guard policy."""

    model_config = ConfigDict(extra="forbid")

    allow_private_networks: bool = Field(
        default=False,
        description="Whether to permit private/internal IP navigations",
    )
    reset_to_about_blank: bool = Field(
        default=True,
        description="Whether document-level redirect violations reset tab to about:blank",
    )
    audit_history_max_size: int = Field(
        default=500,
        ge=10,
        le=5000,
        description="Maximum capacity for in-memory violation audit history",
    )
    custom_blocked_hostnames: list[str] = Field(
        default_factory=lambda: ["169.254.169.254", "instance-data", "metadata.google.internal"],
        description="List of explicitly blocked hostnames",
    )


class HopPolicyConfigResponse(BaseModel):
    """Current policy configuration for redirect hop guard."""

    model_config = ConfigDict(extra="forbid")

    allow_private_networks: bool = Field(..., description="Private network navigation permission")
    reset_to_about_blank: bool = Field(..., description="Tab reset on document violation setting")
    audit_history_max_size: int = Field(..., description="Audit queue capacity")
    custom_blocked_hostnames: list[str] = Field(..., description="Custom blocked hostnames")


class HopViolationRecordResponse(BaseModel):
    """Immutable audit record of an intercepted hop violation."""

    model_config = ConfigDict(extra="forbid")

    timestamp_iso: str = Field(..., description="ISO 8601 UTC timestamp")
    initial_url: str = Field(..., description="Initial navigation URL")
    hop_url: str = Field(..., description="Offending hop target URL")
    resource_type: str = Field(..., description="Resource type")
    disposition: str = Field(..., description="Enforcement disposition applied")
    matched_rule: str = Field(..., description="Security rule triggered")
    reason: str = Field(..., description="Detailed description of violation")


class HopViolationsListResponse(BaseModel):
    """Collection response containing recent hop violations."""

    model_config = ConfigDict(extra="forbid")

    total: int = Field(..., description="Total violation records returned")
    violations: list[HopViolationRecordResponse] = Field(..., description="List of violation records")


class HopSimulationRequest(BaseModel):
    """Payload to simulate and record a hop violation event."""

    model_config = ConfigDict(extra="forbid")

    initial_url: str = Field(..., description="Initial entry URL")
    hop_url: str = Field(..., description="Simulated target hop URL")
    resource_type: str = Field(default="document", description="Resource type")
