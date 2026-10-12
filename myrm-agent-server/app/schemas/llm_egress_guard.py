"""Pydantic DTO schemas for LLM Egress Default-Deny & Credential Binding.

[INPUT]
- None.

[OUTPUT]
- Typed DTO models for egress policy registration, destination inspection,
  and credential binding verification.

[POS]
- Server schemas. Exposes typed contracts for fail-closed LLM egress boundary enforcement.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class DomainAllowlistRuleDto(BaseModel):
    """Configuration for an authorized destination pattern and its bound credentials."""

    model_config = ConfigDict(extra="forbid")

    rule_id: str = Field(..., description="Unique rule identifier (e.g. RULE-OPENAI-01)")
    domain_pattern: str = Field(
        ..., description="Exact domain or wildcard pattern (e.g. *.openai.azure.com)"
    )
    bound_credential_ids: list[str] = Field(
        default_factory=list, description="List of authorized credential identifiers"
    )
    description: str = Field(default="", description="Human-readable rule documentation")
    require_credential_binding: bool = Field(
        default=True, description="Enforce that only bound credentials can be sent"
    )


class SetLlmEgressPolicyRequest(BaseModel):
    """Request payload to install an active LLM egress policy."""

    model_config = ConfigDict(extra="forbid")

    policy_id: str = Field(..., description="Unique policy identifier")
    allowed_rules: list[DomainAllowlistRuleDto] = Field(
        default_factory=list, description="Explicit allowlist rules"
    )
    is_default_deny: bool = Field(
        default=True, description="Strictly reject any un-whitelisted domain"
    )


class LlmEgressPolicyDto(BaseModel):
    """Active LLM egress policy specification."""

    model_config = ConfigDict(extra="forbid")

    policy_id: str = Field(..., description="Policy identifier")
    allowed_rules: list[DomainAllowlistRuleDto] = Field(
        default_factory=list, description="Active allowlist rules"
    )
    is_default_deny: bool = Field(..., description="Default-deny status")
    enforced_at: float = Field(..., description="Timestamp of policy enforcement")


class EvaluateLlmEgressRequest(BaseModel):
    """Request payload to verify an outbound LLM/API call prior to dispatch."""

    model_config = ConfigDict(extra="forbid")

    target_url_or_domain: str = Field(
        ..., description="Target URL or hostname candidate (e.g. https://api.openai.com/v1)"
    )
    presented_credential_id: str | None = Field(
        default=None, description="Identifier of credential proposed for the request"
    )


class LlmEgressVerdictDto(BaseModel):
    """Outcome of egress pre-dispatch inspection."""

    model_config = ConfigDict(extra="forbid")

    verdict: str = Field(
        ...,
        description="PERMITTED, BLOCKED_NO_POLICY, BLOCKED_DOMAIN_NOT_ALLOWED, "
        "BLOCKED_CREDENTIAL_MISMATCH, or BLOCKED_INVALID_TARGET",
    )
    is_permitted: bool = Field(..., description="True if outbound connection is permitted")
    domain: str = Field(..., description="Canonical extracted destination hostname")
    matched_rule_id: str | None = Field(
        default=None, description="Allowlist rule matched if authorized"
    )
    bound_credential_id: str | None = Field(
        default=None, description="Presented credential identifier"
    )
    audit_id: str = Field(..., description="Unique immutable audit event identifier")
    rationale: str = Field(..., description="Evaluation decision trail and explanation")
