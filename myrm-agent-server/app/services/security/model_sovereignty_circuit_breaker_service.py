"""
[POS] app/services/security/model_sovereignty_circuit_breaker_service.py
[INPUT] app.schemas.model_sovereignty_circuit_breaker, myrm_agent_harness.core.security.model_sovereignty_circuit_breaker
[OUTPUT] ModelSovereigntyCircuitBreakerService, get_model_sovereignty_circuit_breaker_service

Service layer for Model Degradation Circuit Breaker & Sovereign Governance Enclave.
Coordinates stealth model swap fingerprinting, automated fallback routing,
and full-stack self-hosted digital sovereignty posture verification.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

import logging

from myrm_agent_harness.core.security.model_sovereignty_circuit_breaker import (
    MeshNodeSpec,
    ModelInferenceProbeInput,
    ModelSovereigntyCircuitBreakerSuite,
    SovereignEnclavePosture,
)

from app.schemas.model_sovereignty_circuit_breaker import (
    AuditSovereigntyRequest,
    DegradationCircuitBreakerMetricsResponse,
    HeartbeatResponse,
    InspectTelemetryRequest,
    InspectTelemetryResponse,
    MeshNodeResponse,
    ModelFingerprintReportResponse,
    RecordHeartbeatRequest,
    RegisterMeshNodeRequest,
    ResetCircuitRequest,
    ResetCircuitResponse,
    RouteRequestPayload,
    RouteRequestResponse,
    SovereignEnclavePostureResponse,
)

logger = logging.getLogger(__name__)


class ModelSovereigntyCircuitBreakerService:
    """Service managing model degradation fingerprint detection and digital sovereignty."""

    def __init__(self, suite: ModelSovereigntyCircuitBreakerSuite | None = None) -> None:
        self._suite = suite or ModelSovereigntyCircuitBreakerSuite()

    def inspect_telemetry(self, request: InspectTelemetryRequest) -> InspectTelemetryResponse:
        """Inspect telemetry for subtle degradation or silent provider swaps."""
        telemetry_input = ModelInferenceProbeInput(
            provider_id=request.provider_id,
            model_name=request.model_name,
            prompt_tokens=request.prompt_tokens,
            completion_tokens=request.completion_tokens,
            latency_ms=request.latency_ms,
            output_text=request.output_text,
            expected_tool_call=request.expected_tool_call,
            valid_tool_call_produced=request.valid_tool_call_produced,
            refusal_detected=request.refusal_detected,
        )
        report, state, did_trip = self._suite.inspect_telemetry(telemetry_input)

        report_response = ModelFingerprintReportResponse(
            provider_id=report.provider_id,
            model_name=report.model_name,
            deviation_score=report.deviation_score,
            severity=report.severity.value,
            is_silent_swap_suspected=report.is_silent_swap_suspected,
            diagnostic_reason=report.diagnostic_reason,
            timestamp=report.timestamp,
        )

        return InspectTelemetryResponse(
            report=report_response,
            circuit_state=state.value,
            did_circuit_trip=did_trip,
        )

    def route_request(self, payload: RouteRequestPayload) -> RouteRequestResponse:
        """Evaluate circuit breaker state to determine routing destination."""
        target, is_fallback = self._suite.route_request(
            provider_id=payload.provider_id,
            fallback_target=payload.fallback_target,
        )
        current_state = self._suite.get_circuit_state(payload.provider_id)

        return RouteRequestResponse(
            selected_target=target,
            is_fallback=is_fallback,
            circuit_state=current_state.value,
        )

    def audit_sovereignty(self, request: AuditSovereigntyRequest) -> SovereignEnclavePostureResponse:
        """Audit full-stack autonomy across data, models, and execution sandboxes."""
        posture: SovereignEnclavePosture = self._suite.audit_sovereignty_posture(
            is_data_self_hosted=request.is_data_self_hosted,
            is_model_self_hosted=request.is_model_self_hosted,
            is_tool_sandbox_isolated=request.is_tool_sandbox_isolated,
            active_storage_mode=request.active_storage_mode,
            active_model_endpoint=request.active_model_endpoint,
        )
        return SovereignEnclavePostureResponse(
            enclave_id=posture.enclave_id,
            is_data_self_hosted=posture.is_data_self_hosted,
            is_model_self_hosted=posture.is_model_self_hosted,
            is_tool_sandbox_isolated=posture.is_tool_sandbox_isolated,
            sovereignty_score=posture.sovereignty_score,
            active_storage_mode=posture.active_storage_mode,
            active_model_endpoint=posture.active_model_endpoint,
            timestamp=posture.timestamp,
        )

    def register_mesh_node(self, request: RegisterMeshNodeRequest) -> MeshNodeResponse:
        """Register a compute node in heterogeneous local mesh."""
        spec: MeshNodeSpec = self._suite.register_mesh_node(
            node_id=request.node_id,
            hostname=request.hostname,
            node_type=request.node_type,
            capacity_weight=request.capacity_weight,
        )
        return self._map_mesh_node(spec)

    def record_heartbeat(self, request: RecordHeartbeatRequest) -> HeartbeatResponse:
        """Record node heartbeat."""
        success = self._suite.record_node_heartbeat(request.node_id)
        return HeartbeatResponse(node_id=request.node_id, success=success)

    def list_healthy_nodes(self) -> list[MeshNodeResponse]:
        """List active mesh nodes with valid heartbeats."""
        nodes = self._suite.list_healthy_nodes()
        return [self._map_mesh_node(n) for n in nodes]

    def get_best_compute_node(self, preferred_type: str = "gpu_worker") -> MeshNodeResponse | None:
        """Retrieve optimal online compute node."""
        node = self._suite.get_best_compute_node(preferred_type)
        if node is None:
            return None
        return self._map_mesh_node(node)

    def reset_circuit(self, request: ResetCircuitRequest) -> ResetCircuitResponse:
        """Reset tripped circuit breaker to healthy CLOSED."""
        self._suite.reset_circuit(request.provider_id)
        current_state = self._suite.get_circuit_state(request.provider_id)
        return ResetCircuitResponse(
            provider_id=request.provider_id,
            circuit_state=current_state.value,
        )

    def get_metrics(self) -> DegradationCircuitBreakerMetricsResponse:
        """Retrieve cumulative metrics."""
        m = self._suite.metrics
        return DegradationCircuitBreakerMetricsResponse(
            fingerprint_inspections_total=m.fingerprint_inspections_total,
            silent_swaps_detected_total=m.silent_swaps_detected_total,
            circuit_trips_total=m.circuit_trips_total,
            circuit_recoveries_total=m.circuit_recoveries_total,
            fallback_reroutes_total=m.fallback_reroutes_total,
            sovereign_audits_total=m.sovereign_audits_total,
        )

    @staticmethod
    def _map_mesh_node(spec: MeshNodeSpec) -> MeshNodeResponse:
        return MeshNodeResponse(
            node_id=spec.node_id,
            hostname=spec.hostname,
            node_type=spec.node_type,
            is_healthy=spec.is_healthy,
            capacity_weight=spec.capacity_weight,
            last_heartbeat=spec.last_heartbeat,
        )


_service_instance: ModelSovereigntyCircuitBreakerService | None = None


def get_model_sovereignty_circuit_breaker_service() -> ModelSovereigntyCircuitBreakerService:
    """Dependency provider for ModelSovereigntyCircuitBreakerService singleton."""
    global _service_instance
    if _service_instance is None:
        _service_instance = ModelSovereigntyCircuitBreakerService()
    return _service_instance
