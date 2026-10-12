"""Pydantic schemas for Tripartite Isolation & Immutable Audit Ledger.

[INPUT]
- None.

[OUTPUT]
- Typed DTO models for Layer-3 audit records, cryptographic chain verification,
  action semantic execution, and zero-knowledge ops telemetry.

[POS]
- Server schemas. Exposes typed contracts for client UI and compliance audit.
"""

from __future__ import annotations

from typing import Union

from pydantic import BaseModel, ConfigDict, Field

JsonScalar = Union[str, int, float, bool, None]


class AuditEvidenceRecordDto(BaseModel):
    """Layer-3 Immutable audit evidence record representation."""

    model_config = ConfigDict(extra="forbid")

    record_id: str = Field(..., description="Unique record identifier")
    sequence_number: int = Field(..., description="Monotonically increasing sequence number")
    prev_hash: str = Field(..., description="SHA-256 hash of previous record or genesis hash")
    record_hash: str = Field(..., description="Cryptographic SHA-256 hash of this record")
    who_user_id: str = Field(..., description="Operator user identifier")
    who_agent_id: str = Field(..., description="Invoking agent identifier")
    when_timestamp: str = Field(..., description="ISO 8601 UTC timestamp")
    rule_version_hash: str = Field(..., description="Active governance ruleset fingerprint")
    tool_name: str = Field(..., description="Name of executed tool")
    tool_call_args_hash: str = Field(..., description="SHA-256 hash of invocation arguments")
    sanitized_args_snapshot: dict[str, JsonScalar] = Field(
        default_factory=dict, description="Redacted arguments snapshot"
    )
    connector_source: str = Field(..., description="MCP server name or connector origin")
    connector_scope: str = Field(..., description="Named tool scope / permission boundary")
    authorized_parameters_hash: str = Field(..., description="Hash of authorized parameters set")
    reconcile_receipt: str = Field(..., description="External receipt or execution outcome hash")


class AppendAuditRecordRequest(BaseModel):
    """Payload to commit an immutable audit record to the ledger."""

    model_config = ConfigDict(extra="forbid")

    who_user_id: str = Field(..., description="Operator user identifier")
    who_agent_id: str = Field(..., description="Invoking agent identifier")
    rule_version_hash: str = Field(..., description="Governance ruleset fingerprint")
    tool_name: str = Field(..., description="Tool name")
    tool_args: dict[str, JsonScalar] = Field(default_factory=dict, description="Raw input arguments")
    connector_source: str = Field(..., description="MCP server or connector source")
    connector_scope: str = Field(..., description="Named tool scope")
    authorized_parameters: list[str] = Field(default_factory=list, description="Authorized parameter names")
    reconcile_receipt: str = Field(..., description="External reconciliation receipt")
    record_id: str | None = Field(default=None, description="Optional explicit record ID")
    when_timestamp: str | None = Field(default=None, description="Optional explicit ISO timestamp")


class VerifyLedgerResponse(BaseModel):
    """Outcome of validating the immutable audit ledger cryptographic hash chain."""

    model_config = ConfigDict(extra="forbid")

    is_valid: bool = Field(..., description="Whether cryptographic hash chain is valid")
    total_records: int = Field(..., description="Total verified records in ledger")
    corrupted_record_id: str | None = Field(default=None, description="First corrupted record ID if invalid")
    reason: str | None = Field(default=None, description="Integrity failure details if corrupted")


class AuditQueryRequest(BaseModel):
    """Filter parameters for querying immutable audit records."""

    model_config = ConfigDict(extra="forbid")

    connector_source: str | None = Field(default=None, description="Filter by MCP server/connector")
    tool_name: str | None = Field(default=None, description="Filter by tool name")
    who_agent_id: str | None = Field(default=None, description="Filter by invoking agent ID")
    start_time: str | None = Field(default=None, description="ISO timestamp start filter")
    end_time: str | None = Field(default=None, description="ISO timestamp end filter")


class AuditQueryResponse(BaseModel):
    """Response containing matched audit records."""

    model_config = ConfigDict(extra="forbid")

    records: list[AuditEvidenceRecordDto] = Field(..., description="List of matched audit records")
    total_matched: int = Field(..., description="Number of matched records")


class ActionSemanticExecutionRequest(BaseModel):
    """Request to invoke an action under strict semantic mode boundaries."""

    model_config = ConfigDict(extra="forbid")

    mode: str = Field(..., description="Semantic mode: REPLAY_LOG, OFFLINE_EVAL, RE_EXECUTE")
    tool_name: str = Field(..., description="Target tool name")
    action_payload: str = Field(default="", description="Payload or parameter description")
    audit_record_id: str | None = Field(default=None, description="Pre-committed audit record ID for RE_EXECUTE")
    explicit_confirmed: bool = Field(default=False, description="Explicit operator confirmation flag")


class ActionSemanticExecutionResponse(BaseModel):
    """Outcome of action execution under semantic mode."""

    model_config = ConfigDict(extra="forbid")

    mode: str = Field(..., description="Executed semantic mode")
    tool_name: str = Field(..., description="Target tool name")
    executed: bool = Field(..., description="Whether real execution occurred")
    is_simulated: bool = Field(..., description="Whether result is mocked/simulated")
    result: str = Field(..., description="Output or simulation message")
    audit_record_id: str | None = Field(default=None, description="Associated audit record ID if executed")


class OpsRegisterTaskRequest(BaseModel):
    """Register a running task with operational telemetry."""

    model_config = ConfigDict(extra="forbid")

    task_id: str = Field(..., description="Unique task identifier")
    agent_id: str = Field(..., description="Responsible agent identifier")
    memory_bytes: int = Field(default=1048576, description="Memory footprint in bytes")


class OpsTelemetryDto(BaseModel):
    """Zero-knowledge operational telemetry record without business payloads."""

    model_config = ConfigDict(extra="forbid")

    task_id: str = Field(..., description="Task identifier")
    agent_id: str = Field(..., description="Agent identifier")
    runtime_ms: int = Field(..., description="Elapsed runtime in milliseconds")
    memory_bytes: int = Field(..., description="Allocated memory in bytes")
    state: str = Field(..., description="Operational status: RUNNING, STOPPED_BY_OPS, etc.")


class OpsForceStopRequest(BaseModel):
    """Ops-level force stop without reading conversation content."""

    model_config = ConfigDict(extra="forbid")

    task_id: str = Field(..., description="Task identifier to terminate")
    operator_id: str = Field(..., description="Ops engineer identifier")


class OpsForceStopResponse(BaseModel):
    """Outcome of ops force stop action."""

    model_config = ConfigDict(extra="forbid")

    task_id: str = Field(..., description="Task identifier")
    stopped: bool = Field(..., description="Whether stop signal was accepted")
    message: str = Field(..., description="Result message")
