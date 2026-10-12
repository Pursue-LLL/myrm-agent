"""Pydantic schemas for Spatiotemporal Duality, Connector Trust & Declarative Saga.

[INPUT]
- None.

[OUTPUT]
- Typed DTO models for connector trust leases, tool execution requests/responses,
  saga rollbacks, and emission audit logs.

[POS]
- Server schemas. Exposes typed contracts for client UI and administrative control.
"""

from __future__ import annotations

from typing import Union

from pydantic import BaseModel, ConfigDict, Field

JsonScalar = Union[str, int, float, bool, None]


class ConnectorTrustLeaseDto(BaseModel):
    """Explicit trust authorization grant issued to an external connector."""

    model_config = ConfigDict(extra="forbid")

    lease_id: str = Field(..., description="Unique lease identifier")
    connector_id: str = Field(..., description="Connector identifier")
    host: str = Field(..., description="Authorized target host")
    authorized_scopes: list[str] = Field(..., description="Authorized scope permissions")
    expires_at: str = Field(..., description="ISO 8601 UTC expiration timestamp")
    is_active: bool = Field(default=True, description="Whether lease is currently active")


class GrantTrustLeaseRequest(BaseModel):
    """Payload to grant a new trust authorization lease to an external connector."""

    model_config = ConfigDict(extra="forbid")

    connector_id: str = Field(..., description="Connector identifier")
    host: str = Field(..., description="Target host to trust")
    authorized_scopes: list[str] = Field(..., description="List of authorized scope strings")
    ttl_seconds: int = Field(default=3600, description="Lease duration in seconds")


class RevokeTrustLeaseRequest(BaseModel):
    """Payload to revoke an active connector trust lease."""

    model_config = ConfigDict(extra="forbid")

    lease_id: str = Field(..., description="Lease identifier to revoke")


class RevokeTrustLeaseResponse(BaseModel):
    """Outcome of lease revocation."""

    model_config = ConfigDict(extra="forbid")

    revoked: bool = Field(..., description="Whether lease was revoked")
    lease_id: str = Field(..., description="Revoked lease identifier")


class EmissionAuditRecordDto(BaseModel):
    """Immutable audit record representing a physical emission operation."""

    model_config = ConfigDict(extra="forbid")

    audit_id: str = Field(..., description="Unique audit record identifier")
    agent_id: str = Field(..., description="Initiating agent identifier")
    approver_id: str = Field(..., description="Approving user or system identifier")
    connector_id: str = Field(..., description="Target external connector identifier")
    tool_name: str = Field(..., description="Executed tool name")
    params_hash: str = Field(..., description="SHA-256 fingerprint of input parameters")
    receipt: str = Field(..., description="External system execution receipt summary")
    compensation_status: str = Field(..., description="Status of reverse compensation action")
    timestamp: str = Field(..., description="ISO 8601 UTC execution timestamp")


class ExecuteDualToolRequest(BaseModel):
    """Payload to invoke a tool respecting spatiotemporal duality and security gates."""

    model_config = ConfigDict(extra="forbid")

    tool_name: str = Field(..., description="Target tool name")
    intent: str = Field(default="ACQUISITION", description="ACQUISITION or EMISSION")
    params: dict[str, JsonScalar] = Field(default_factory=dict, description="Input tool arguments")
    agent_id: str = Field(..., description="Calling agent identifier")
    approver_id: str | None = Field(default=None, description="Optional approving user identifier")
    connector_id: str | None = Field(default=None, description="External connector identifier for emission")
    connector_host: str | None = Field(default=None, description="External connector host for emission")
    required_scope: str | None = Field(default=None, description="Required authorization scope")
    hitl_confirmed: bool = Field(
        default=False, description="Explicit secondary HITL confirmation for emission"
    )
    compensator_name: str | None = Field(default=None, description="Registered compensating hook name")
    compensation_params: dict[str, JsonScalar] = Field(
        default_factory=dict, description="Parameters to pass to the compensating action"
    )


class ExecuteDualToolResponse(BaseModel):
    """Outcome of tool execution under spatiotemporal duality rules."""

    model_config = ConfigDict(extra="forbid")

    tool_name: str = Field(..., description="Executed tool name")
    intent: str = Field(..., description="Action intent (ACQUISITION or EMISSION)")
    output: str = Field(..., description="Output produced by tool action")
    audit_record: EmissionAuditRecordDto | None = Field(
        default=None, description="Emission audit record if applicable"
    )


class SagaRollbackResponse(BaseModel):
    """Outcome of triggering reverse LIFO Saga rollback."""

    model_config = ConfigDict(extra="forbid")

    total_steps_rolled_back: int = Field(..., description="Number of compensated steps")
    success: bool = Field(..., description="Whether all compensations succeeded")
    details: list[tuple[str, bool]] = Field(..., description="Per-step compensation results")
