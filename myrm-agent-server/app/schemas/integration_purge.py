"""Schemas for integration retained context governance, purge, and provenance revocation.

[INPUT]
- datetime::{UTC, datetime}
- pydantic::{BaseModel, Field}

[OUTPUT]
- RetainedContextSummaryResponse: Detailed snapshot of retained context items
- DisconnectWithPurgeRequest: Request payload selecting disconnect and purge mode
- DisconnectWithPurgeResponse: Result summary of the disconnect & purge operation
- ProvenanceRevocationAuditItem: Audit ledger item for provenance revocation

[POS]
Server schemas supporting GDPR/Privacy-compliant connector disconnection,
retained memory accounting, and tamper-evident provenance revocation (Topic 01 Item 179).
"""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, Field


class RetainedContextSummaryResponse(BaseModel):
    """Auditing summary of context items retained from an external integration."""

    integration_id: str = Field(description="Connector identifier (e.g. google_workspace, github, mcp:fs)")
    provider_type: str = Field(
        default="external_integration",
        description="Type category: oauth_provider, mcp_server, or external_integration",
    )
    retained_memory_count: int = Field(
        default=0, ge=0, description="Count of semantic/vector memories retaining this provenance"
    )
    retained_tree_count: int = Field(
        default=0, ge=0, description="Count of hierarchical integration trees retained"
    )
    retained_fact_count: int = Field(
        default=0, ge=0, description="Count of relational facts retaining this provenance"
    )
    total_retained_items: int = Field(
        default=0, ge=0, description="Total count of retained items across all stores"
    )
    oldest_retained_at: str | None = Field(
        default=None, description="ISO timestamp of earliest retained item"
    )
    latest_retained_at: str | None = Field(
        default=None, description="ISO timestamp of most recent retained item"
    )
    sample_snippets: list[str] = Field(
        default_factory=list, description="Sanitized snippets for transparent user review"
    )
    is_provenance_revoked: bool = Field(
        default=False, description="Whether this integration provenance is currently revoked"
    )


class DisconnectWithPurgeRequest(BaseModel):
    """Payload to execute connector disconnect with optional retained context purge."""

    purge_mode: str = Field(
        default="retain_context",
        description="Selected mode: 'retain_context' (Dots default), 'selective_purge', or 'purge_and_revoke'",
    )
    confirm_purge: bool = Field(
        default=False,
        description="Explicit user confirmation flag required for destructive purge modes",
    )
    reason: str = Field(
        default="",
        description="Optional audit rationale for provenance revocation and context cleanup",
    )


class DisconnectWithPurgeResponse(BaseModel):
    """Response returned upon completion of disconnect and purge action."""

    integration_id: str = Field(description="Target connector or integration identifier")
    provider_type: str = Field(description="Connector category")
    disconnected: bool = Field(default=True, description="Whether credential/access was disconnected")
    purged_items: int = Field(default=0, ge=0, description="Number of context items physically purged")
    mode: str = Field(description="Executed purge mode")
    revocation_id: str | None = Field(
        default=None, description="Identifier of the recorded provenance revocation entry if revoked"
    )
    message: str = Field(description="Status message summarizing execution outcome")
    completed_at: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
        description="ISO timestamp when the operation concluded",
    )


class ProvenanceRevocationAuditItem(BaseModel):
    """Audit ledger record representing a revoked provenance origin."""

    revocation_id: str = Field(description="Unique revocation record identifier")
    integration_id: str = Field(description="Target connector identifier")
    reason: str = Field(description="Recorded rationale for revocation")
    revoked_at: str = Field(description="ISO timestamp of revocation")
    purged_items_count: int = Field(ge=0, description="Number of items purged at revocation")
    actor: str = Field(description="Subject who triggered the revocation")
