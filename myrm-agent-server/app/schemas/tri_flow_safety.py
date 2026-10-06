"""Pydantic schemas for Agentic Transaction Safety and Tri-Flow Isolation.

[INPUT]
- None (Self-contained Pydantic schemas)

[OUTPUT]
- ToolCallVerificationRequest, ToolCallVerificationResponse, EndpointValidationRequest
- EndpointValidationResponse, SanitizeLogsRequest, SanitizeLogsResponse

[POS]
Schema definitions for agentic transaction safety pillars and tri-flow isolation.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

WorkflowRoleType = Literal["read_only", "buyer", "seller"]


class ToolCallVerificationRequest(BaseModel):
    """Payload to verify if a tool call is permitted under the active workflow role."""

    role: WorkflowRoleType = Field(..., description="Active workflow role")
    tool_name: str = Field(..., description="Target tool name to invoke")
    amount: float = Field(0.0, description="Financial transaction amount if applicable")
    hitl_confirmed: bool = Field(
        False, description="Whether human confirmation was explicitly granted"
    )


class ToolCallVerificationResponse(BaseModel):
    """Verification outcome of tool call under tri-flow isolation."""

    is_allowed: bool = Field(..., description="Whether invocation is permitted")
    current_role: WorkflowRoleType = Field(..., description="Evaluated workflow role")
    tool_name: str = Field(..., description="Tool evaluated")
    reason: str = Field(..., description="Defense decision rationale")
    requires_hitl: bool = Field(
        False, description="Whether execution requires HITL confirmation"
    )


class EndpointValidationRequest(BaseModel):
    """Payload to inspect destination API, RPC, or contract method before dispatching."""

    service: str = Field(..., description="Target connector or service name")
    path: str = Field(..., description="Target endpoint path")
    method: str = Field("GET", description="HTTP method")
    function_name: str | None = Field(
        None, description="Smart contract ABI function name if applicable"
    )


class EndpointValidationResponse(BaseModel):
    """Zero-guesswork validation outcome for outgoing endpoint call."""

    is_allowed: bool = Field(..., description="Whether endpoint call is permitted")
    service: str = Field(..., description="Evaluated service")
    endpoint: str = Field(..., description="Evaluated endpoint path")
    method: str = Field(..., description="Evaluated HTTP method")
    reason: str = Field(..., description="Detailed safety rationale")


class SanitizeLogsRequest(BaseModel):
    """Payload containing raw stdout/log text to scan and redact."""

    raw_text: str = Field(..., description="Raw text containing logs or prompts")


class SanitizeLogsResponse(BaseModel):
    """Result of zero-print redaction scan."""

    sanitized_text: str = Field(..., description="Text with private keys redacted")
    redactions_count: int = Field(..., description="Number of sensitive keys scrubbed")
    detected_types: list[str] = Field(..., description="Categories of credentials scrubbed")


class RegisterToolContractRequest(BaseModel):
    """Request to register or update a tool role contract."""

    tool_name: str = Field(..., description="Tool name")
    allowed_roles: list[WorkflowRoleType] = Field(
        ..., description="Permitted workflow roles"
    )
    is_financial_transaction: bool = Field(
        False, description="Whether tool performs financial transfer"
    )
    requires_hitl_confirmation: bool = Field(
        False, description="Whether tool always requires human confirmation"
    )
    financial_threshold: float = Field(
        0.0, description="Amount above which confirmation is mandatory"
    )


class RegisterEndpointSpecRequest(BaseModel):
    """Request to register a documented endpoint whitelist spec."""

    service: str = Field(..., description="Service identifier")
    path: str = Field(..., description="Documented URL or path pattern")
    allowed_methods: list[str] = Field(
        default=["GET"], description="Allowed HTTP methods"
    )
    contract_functions: list[str] = Field(
        default=[], description="Allowed contract ABI functions"
    )
