"""Pydantic schemas for Integration Egress Trust disclosures.

[INPUT]
- None.

[OUTPUT]
- Typed DTO models for pre-connect disclosure cards and provider token revocation contracts.

[POS]
- Server schemas. Exposes typed contracts for the client UI connection wizard.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class PreConnectDisclosureDto(BaseModel):
    """Pre-connect disclosure card explaining access scope and data lifecycle to user."""

    model_config = ConfigDict(extra="forbid")

    provider_id: str = Field(..., description="Unique integration provider identifier")
    display_name: str = Field(..., description="Human-readable provider display name")
    data_types_read: list[str] = Field(..., description="Specific data types accessed by integration")
    actions_performed: list[str] = Field(..., description="Actions performed on user behalf")
    storage_locations: list[str] = Field(..., description="Where synced data and memory trees reside")
    purge_policy_summary: str = Field(..., description="Clear summary of what is deleted upon disconnect")
    flow_direction: str = Field(..., description="READ_INGRESS, WRITE_EGRESS, or BIDIRECTIONAL")


class ProviderRevokeConfigDto(BaseModel):
    """Token revocation capabilities declared for a provider."""

    model_config = ConfigDict(extra="forbid")

    provider_id: str = Field(..., description="Provider identifier")
    revocation_endpoint: str | None = Field(default=None, description="External OAuth token revocation URL")
    supports_remote_revoke: bool = Field(..., description="Whether provider supports automated remote token revocation")
    manual_revoke_url: str | None = Field(default=None, description="Direct URL where user can manually revoke permissions")
