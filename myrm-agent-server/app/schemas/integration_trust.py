"""Pydantic schemas for Integration Egress Trust Lifecycle.

[INPUT]
- None.

[OUTPUT]
- Typed DTO models for pre-connect disclosure cards, disconnect purge receipts,
  and provider token revocation contracts.

[POS]
- Server schemas. Exposes typed contracts for client UI connection wizard and disconnect dialogs.
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
    revocation_endpoint: str | None = Field(
        default=None, description="External OAuth token revocation URL"
    )
    supports_remote_revoke: bool = Field(
        ..., description="Whether provider supports automated remote token revocation"
    )
    manual_revoke_url: str | None = Field(
        default=None, description="Direct URL where user can manually revoke permissions"
    )


class DisconnectPurgeReceiptDto(BaseModel):
    """Audit receipt confirming memory tree purge and provider revocation."""

    model_config = ConfigDict(extra="forbid")

    provider_id: str = Field(..., description="Disconnected provider ID")
    cleared_memory_trees: int = Field(..., description="Number of synced memory trees purged")
    cleared_documents: int = Field(..., description="Number of synced document entries purged")
    revocation_status: str = Field(
        ..., description="Outcome: REVOKED_REMOTE, REVOKED_LOCAL_ONLY, NOT_SUPPORTED, etc."
    )
    revocation_receipt: str | None = Field(
        default=None, description="Cryptographic or server-side token revocation receipt"
    )
    manual_revoke_url: str | None = Field(
        default=None, description="Manual revocation URL if remote revoke unsupported"
    )
    timestamp: str = Field(..., description="ISO 8601 UTC timestamp of disconnection")


class DisconnectIntegrationRequest(BaseModel):
    """Payload to execute atomic disconnect and purification for an integration."""

    model_config = ConfigDict(extra="forbid")

    provider_id: str = Field(..., description="Provider identifier to disconnect")
    purge_synced_data: bool = Field(
        default=True,
        description="Whether to purge synced memory trees and documents (Purge-on-Disconnect)",
    )


class DisconnectIntegrationResponse(BaseModel):
    """Response of atomic disconnect operation."""

    model_config = ConfigDict(extra="forbid")

    receipt: DisconnectPurgeReceiptDto = Field(..., description="Disconnection and purge receipt")
    success: bool = Field(..., description="Whether disconnect completed successfully")
