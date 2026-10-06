"""Pydantic schemas for Multi-Tenant Data Isolation and Cross-Contamination Probes.

[INPUT]
- None (Self-contained Pydantic schemas)

[OUTPUT]
- TenantMemoryContextSchema, CompilePartitionKeyRequest, CompilePartitionKeyResponse
- RunIsolationAuditRequest, DataSovereigntyReportResponse

[POS]
Schema definitions for multi-tenant data isolation and cross-contamination probes.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

ScopeLevelType = Literal["user", "agent", "session", "global"]
EnvironmentType = Literal["local_standalone", "cloud_dedicated_sandbox"]


class TenantMemoryContextSchema(BaseModel):
    """Context identifying tenant and agent memory partition."""

    user_id: str = Field(..., description="Unique tenant or user identifier")
    agent_id: str = Field(..., description="Agent bound to the memory partition")
    session_id: str | None = Field(None, description="Optional active session ID")
    scope: ScopeLevelType = Field(
        default="agent", description="Memory isolation scope level"
    )


class CompilePartitionKeyRequest(BaseModel):
    """Request payload to compile a composite partition key."""

    context: TenantMemoryContextSchema = Field(..., description="Tenant memory context")


class CompilePartitionKeyResponse(BaseModel):
    """Response returned upon compiling a tamper-evident partition key."""

    composite_key: str = Field(..., description="Compiled composite partition key")
    user_id: str = Field(..., description="Sanitized user ID")
    agent_id: str = Field(..., description="Sanitized agent ID")
    scope: str = Field(..., description="Applied isolation scope")
    namespace_digest: str = Field(..., description="Cryptographic partition digest")


class ProbeScenarioResultSchema(BaseModel):
    """Result of an individual synthetic adversarial isolation probe."""

    scenario: str = Field(..., description="Test scenario category")
    probe_query: str = Field(..., description="Synthetic probe query string")
    expected_matches: int = Field(..., description="Expected safe matches count")
    actual_matches: int = Field(..., description="Actual returned matches count")
    cross_hits: int = Field(0, description="Cross-tenant leakage count (must be 0)")
    is_isolated: bool = Field(..., description="Whether scenario is strictly isolated")
    details: str = Field(..., description="Diagnostic details")


class RunIsolationAuditRequest(BaseModel):
    """Payload to trigger synthetic adversarial cross-tenant isolation audit."""

    context: TenantMemoryContextSchema = Field(..., description="Target tenant context")
    environment_type: EnvironmentType = Field(
        default="local_standalone",
        description="Deployment environment (standalone vs sandbox)",
    )


class DataSovereigntyReportResponse(BaseModel):
    """Full data sovereignty and physical isolation self-inspection audit card."""

    environment_type: str = Field(..., description="Deployment topology")
    total_probes_run: int = Field(..., description="Total synthetic probes evaluated")
    cross_hits_count: int = Field(..., description="Cross-tenant leakage count (must be 0)")
    isolation_pass_rate: float = Field(..., description="Isolation pass rate percentage")
    is_safe: bool = Field(..., description="Overall isolation security assertion")
    partition_integrity_verified: bool = Field(
        ..., description="Whether partition key integrity passed verification"
    )
    scenario_results: list[ProbeScenarioResultSchema] = Field(
        default_factory=list, description="Detailed probe breakdown"
    )
    summary: str = Field(..., description="Executive compliance summary")
