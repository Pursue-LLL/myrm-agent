"""
[POS] app/schemas/target_scope_boundary.py
[INPUT] pydantic
[OUTPUT] SetContractRequest, TargetScopeContractResponse, VerifyTargetRequest, ScopeVerificationResponse, KillSwitchStatusResponse, TargetScopeMetricsResponse

Pydantic schemas for Strict Target Scope Authorization & Egress Boundary Suite.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class SetContractRequest(BaseModel):
    """Payload to configure the active Rules of Engagement (ROE) scope contract."""

    contract_id: str = Field(..., description="Unique ROE contract identifier")
    engagement_name: str = Field(..., description="Name of pentest engagement or security audit")
    authorized_domains: list[str] = Field(default_factory=list, description="Permitted domains or wildcards (e.g. *.example.com)")
    authorized_cidrs: list[str] = Field(default_factory=list, description="Permitted IPv4/IPv6 CIDRs or subnets")
    prohibited_targets: list[str] = Field(default_factory=list, description="Explicitly blacklisted domains, subnets, or services")
    signed_by: str = Field(..., description="Identity or officer signing the authorization")
    signature_hash: str = Field(..., description="Cryptographic signature digest of ROE contract")
    is_active: bool = Field(default=True, description="Whether contract is active")


class TargetScopeContractResponse(BaseModel):
    """Details of active ROE target scope contract."""

    contract_id: str = Field(..., description="Contract ID")
    engagement_name: str = Field(..., description="Engagement name")
    authorized_domains: list[str] = Field(..., description="Authorized domains")
    authorized_cidrs: list[str] = Field(..., description="Authorized CIDRs")
    prohibited_targets: list[str] = Field(..., description="Prohibited targets")
    signed_by: str = Field(..., description="Signer identity")
    signature_hash: str = Field(..., description="Signature hash")
    is_active: bool = Field(..., description="Active status")


class VerifyTargetRequest(BaseModel):
    """Payload to evaluate an outbound network connection destination."""

    target_host: str = Field(..., description="Destination hostname, domain, or IP address")
    resolved_ip: str | None = Field(default=None, description="Optional DNS-resolved IP address for secondary verification")


class ScopeVerificationResponse(BaseModel):
    """Enforcement evaluation outcome for outbound connection attempt."""

    is_allowed: bool = Field(..., description="Whether connection is permitted under active ROE")
    verdict: str = Field(..., description="Enforcement verdict code: IN_SCOPE_ALLOWED, OUT_OF_SCOPE_BLOCKED, etc.")
    target_host: str = Field(..., description="Evaluated destination host")
    resolved_ip: str | None = Field(default=None, description="Resolved IP if evaluated")
    diagnostic_reason: str = Field(..., description="Diagnostic justification for verdict")
    contract_id: str | None = Field(default=None, description="Active contract ID used for evaluation")


class KillSwitchStatusResponse(BaseModel):
    """Current status of the emergency scanning kill-switch."""

    is_kill_switch_active: bool = Field(..., description="Whether emergency kill-switch is engaged")
    message: str = Field(..., description="Diagnostic explanation of state")


class TargetScopeMetricsResponse(BaseModel):
    """Cumulative metrics tracking scope verifications and egress interceptions."""

    scope_checks_total: int = Field(..., description="Total target verifications performed")
    in_scope_allowed_total: int = Field(..., description="Total authorized in-scope connections permitted")
    out_of_scope_blocked_total: int = Field(..., description="Total out-of-scope connections intercepted")
    metadata_probes_blocked_total: int = Field(..., description="Total cloud metadata access attempts blocked")
    kill_switch_activations_total: int = Field(..., description="Total emergency kill-switch activations")
