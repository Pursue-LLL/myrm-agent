"""
[POS] app/schemas/model_sovereignty_circuit_breaker.py
[INPUT] pydantic
[OUTPUT] InspectTelemetryRequest, ModelFingerprintReportResponse, InspectTelemetryResponse, RouteRequestPayload, RouteRequestResponse, AuditSovereigntyRequest, SovereignEnclavePostureResponse, RegisterMeshNodeRequest, MeshNodeResponse, RecordHeartbeatRequest, HeartbeatResponse, ResetCircuitRequest, ResetCircuitResponse, DegradationCircuitBreakerMetricsResponse

Pydantic schemas for Model Degradation Circuit Breaker & Sovereign Governance Enclave.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class InspectTelemetryRequest(BaseModel):
    """Payload capturing model inference output telemetry for degradation analysis."""

    provider_id: str = Field(..., description="Unique LLM provider identifier")
    model_name: str = Field(..., description="Target model name")
    prompt_tokens: int = Field(..., ge=0, description="Tokens in input prompt")
    completion_tokens: int = Field(..., ge=0, description="Tokens in model output")
    latency_ms: float = Field(..., ge=0.0, description="End-to-end inference latency in milliseconds")
    output_text: str = Field(..., description="Raw generated text from model")
    expected_tool_call: bool = Field(default=False, description="Whether prompt strictly requested a tool call")
    valid_tool_call_produced: bool = Field(default=True, description="Whether generated output contains valid tool call syntax")
    refusal_detected: bool = Field(default=False, description="Whether unexpected safety refusal was triggered")


class ModelFingerprintReportResponse(BaseModel):
    """Diagnostic report evaluating output against expected baseline fingerprint."""

    provider_id: str = Field(..., description="LLM provider identifier")
    model_name: str = Field(..., description="Model name")
    deviation_score: float = Field(..., ge=0.0, le=1.0, description="Deviation score from 0.0 to 1.0")
    severity: str = Field(..., description="Severity level: NORMAL, SLIGHT_DEVIATION, SEVERE_DOWNGRADE, TOTAL_OUTAGE")
    is_silent_swap_suspected: bool = Field(..., description="Whether silent model swap or degradation is suspected")
    diagnostic_reason: str = Field(..., description="Explanation of evaluation findings")
    timestamp: float = Field(..., description="Timestamp of inspection")


class InspectTelemetryResponse(BaseModel):
    """Response payload containing fingerprint analysis and updated circuit state."""

    report: ModelFingerprintReportResponse = Field(..., description="Fingerprint evaluation report")
    circuit_state: str = Field(..., description="Updated circuit breaker state: CLOSED, OPEN, HALF_OPEN")
    did_circuit_trip: bool = Field(..., description="Whether this inspection tripped the circuit to OPEN")


class RouteRequestPayload(BaseModel):
    """Payload determining dynamic endpoint routing based on circuit state."""

    provider_id: str = Field(..., description="Primary provider ID")
    fallback_target: str = Field(..., description="Fallback endpoint or model to route to if circuit is OPEN")


class RouteRequestResponse(BaseModel):
    """Result of circuit breaker routing determination."""

    selected_target: str = Field(..., description="Routing target selected by circuit state")
    is_fallback: bool = Field(..., description="True if routed to fallback endpoint due to OPEN circuit")
    circuit_state: str = Field(..., description="Current circuit state for the provider")


class AuditSovereigntyRequest(BaseModel):
    """Request payload auditing full-stack self-hosted digital sovereignty posture."""

    is_data_self_hosted: bool = Field(default=True, description="Whether user data and memories reside on local storage")
    is_model_self_hosted: bool = Field(default=False, description="Whether model inference runs on local hardware")
    is_tool_sandbox_isolated: bool = Field(default=True, description="Whether tool execution runs in isolated sandbox")
    active_storage_mode: str = Field(default="sqlite_local_volume", description="Storage backend descriptor")
    active_model_endpoint: str = Field(default="http://localhost:11434", description="Active model endpoint URI")


class SovereignEnclavePostureResponse(BaseModel):
    """Evaluation result of data, model, and tool self-hosted digital sovereignty."""

    enclave_id: str = Field(..., description="Unique enclave audit ID")
    is_data_self_hosted: bool = Field(..., description="Whether data is self-hosted")
    is_model_self_hosted: bool = Field(..., description="Whether model is self-hosted")
    is_tool_sandbox_isolated: bool = Field(..., description="Whether tool sandbox is isolated")
    sovereignty_score: int = Field(..., ge=0, le=100, description="Overall digital sovereignty score (0-100)")
    active_storage_mode: str = Field(..., description="Active storage backend")
    active_model_endpoint: str = Field(..., description="Active model endpoint URI")
    timestamp: float = Field(..., description="Audit timestamp")


class RegisterMeshNodeRequest(BaseModel):
    """Payload registering a compute node into heterogeneous local mesh."""

    node_id: str = Field(..., description="Unique node ID")
    hostname: str = Field(..., description="LAN or host domain name")
    node_type: str = Field(..., description="Compute category: workstation, gpu_worker, edge_node")
    capacity_weight: int = Field(default=10, ge=1, le=100, description="Relative compute capacity weight")


class MeshNodeResponse(BaseModel):
    """Specification of a registered compute node in local mesh."""

    node_id: str = Field(..., description="Unique node ID")
    hostname: str = Field(..., description="Hostname")
    node_type: str = Field(..., description="Node compute type")
    is_healthy: bool = Field(..., description="Health status based on heartbeat")
    capacity_weight: int = Field(..., description="Capacity weight")
    last_heartbeat: float = Field(..., description="Timestamp of latest heartbeat")


class RecordHeartbeatRequest(BaseModel):
    """Heartbeat signal from a mesh compute node."""

    node_id: str = Field(..., description="Target node ID")


class HeartbeatResponse(BaseModel):
    """Heartbeat acknowledgement result."""

    node_id: str = Field(..., description="Target node ID")
    success: bool = Field(..., description="Whether heartbeat was successfully recorded")


class ResetCircuitRequest(BaseModel):
    """Request resetting a tripped circuit breaker."""

    provider_id: str = Field(..., description="Target provider ID to reset")


class ResetCircuitResponse(BaseModel):
    """Result of circuit reset."""

    provider_id: str = Field(..., description="Reset provider ID")
    circuit_state: str = Field(..., description="New circuit state (CLOSED)")


class DegradationCircuitBreakerMetricsResponse(BaseModel):
    """Cumulative operational metrics for degradation breaker and sovereign enclave."""

    fingerprint_inspections_total: int = Field(..., description="Total inference telemetry checks performed")
    silent_swaps_detected_total: int = Field(..., description="Total suspected model swaps detected")
    circuit_trips_total: int = Field(..., description="Total circuit trips to OPEN state")
    circuit_recoveries_total: int = Field(..., description="Total circuit recoveries to CLOSED")
    fallback_reroutes_total: int = Field(..., description="Total requests rerouted to fallback targets")
    sovereign_audits_total: int = Field(..., description="Total digital sovereignty audits conducted")
