"""
Unit tests for Model Sovereignty Circuit Breaker & Sovereign Governance Service.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from app.schemas.model_sovereignty_circuit_breaker import (
    AuditSovereigntyRequest,
    InspectTelemetryRequest,
    RecordHeartbeatRequest,
    RegisterMeshNodeRequest,
    ResetCircuitRequest,
    RouteRequestPayload,
)
from app.services.security.model_sovereignty_circuit_breaker_service import (
    ModelSovereigntyCircuitBreakerService,
)


def test_service_inspect_telemetry_normal() -> None:
    service = ModelSovereigntyCircuitBreakerService()
    req = InspectTelemetryRequest(
        provider_id="claude-cloud",
        model_name="claude-3-opus",
        prompt_tokens=150,
        completion_tokens=300,
        latency_ms=950.0,
        output_text="Complete response with thorough reasoning.",
        expected_tool_call=False,
        valid_tool_call_produced=True,
        refusal_detected=False,
    )
    resp = service.inspect_telemetry(req)
    assert resp.circuit_state == "CLOSED"
    assert not resp.did_circuit_trip
    assert not resp.report.is_silent_swap_suspected
    assert resp.report.severity == "NORMAL"


def test_service_inspect_telemetry_outage_trips_circuit() -> None:
    service = ModelSovereigntyCircuitBreakerService()
    req_fail = InspectTelemetryRequest(
        provider_id="failing-cloud",
        model_name="unstable-model",
        prompt_tokens=100,
        completion_tokens=0,
        latency_ms=50.0,
        output_text="",
        expected_tool_call=False,
        valid_tool_call_produced=True,
    )

    # First failure -> recorded but doesn't trip yet (threshold=2)
    resp1 = service.inspect_telemetry(req_fail)
    assert resp1.circuit_state == "CLOSED"
    assert not resp1.did_circuit_trip
    assert resp1.report.is_silent_swap_suspected

    # Second failure -> trips circuit to OPEN
    resp2 = service.inspect_telemetry(req_fail)
    assert resp2.circuit_state == "OPEN"
    assert resp2.did_circuit_trip


def test_service_route_request() -> None:
    service = ModelSovereigntyCircuitBreakerService()
    payload = RouteRequestPayload(
        provider_id="primary-llm",
        fallback_target="local-ollama-qwen",
    )

    # Initial healthy state routes to primary
    r1 = service.route_request(payload)
    assert r1.selected_target == "primary-llm"
    assert not r1.is_fallback
    assert r1.circuit_state == "CLOSED"

    # Trip breaker
    fail_req = InspectTelemetryRequest(
        provider_id="primary-llm",
        model_name="primary-llm",
        prompt_tokens=100,
        completion_tokens=0,
        latency_ms=10.0,
        output_text="",
    )
    service.inspect_telemetry(fail_req)
    service.inspect_telemetry(fail_req)

    # Now routes to fallback
    r2 = service.route_request(payload)
    assert r2.selected_target == "local-ollama-qwen"
    assert r2.is_fallback
    assert r2.circuit_state == "OPEN"


def test_service_audit_sovereignty() -> None:
    service = ModelSovereigntyCircuitBreakerService()
    req = AuditSovereigntyRequest(
        is_data_self_hosted=True,
        is_model_self_hosted=True,
        is_tool_sandbox_isolated=True,
        active_storage_mode="sqlite_local_volume",
        active_model_endpoint="http://127.0.0.1:8000/v1",
    )
    resp = service.audit_sovereignty(req)
    assert resp.sovereignty_score == 100
    assert resp.is_data_self_hosted
    assert resp.is_model_self_hosted
    assert resp.is_tool_sandbox_isolated


def test_service_mesh_node_lifecycle_and_best_node() -> None:
    service = ModelSovereigntyCircuitBreakerService()

    reg1 = RegisterMeshNodeRequest(
        node_id="macbook-pro",
        hostname="mbp.local",
        node_type="gpu_worker",
        capacity_weight=25,
    )
    n1 = service.register_mesh_node(reg1)
    assert n1.node_id == "macbook-pro"
    assert n1.is_healthy

    reg2 = RegisterMeshNodeRequest(
        node_id="homelab-pc",
        hostname="pc.local",
        node_type="gpu_worker",
        capacity_weight=50,
    )
    service.register_mesh_node(reg2)

    nodes = service.list_healthy_nodes()
    assert len(nodes) == 2

    best = service.get_best_compute_node(preferred_type="gpu_worker")
    assert best is not None
    assert best.node_id == "homelab-pc"  # higher weight (50 vs 25)

    hb = service.record_heartbeat(RecordHeartbeatRequest(node_id="macbook-pro"))
    assert hb.success


def test_service_reset_circuit_and_metrics() -> None:
    service = ModelSovereigntyCircuitBreakerService()

    # Trip breaker
    fail_req = InspectTelemetryRequest(
        provider_id="trip-target",
        model_name="model-x",
        prompt_tokens=100,
        completion_tokens=0,
        latency_ms=10.0,
        output_text="",
    )
    service.inspect_telemetry(fail_req)
    service.inspect_telemetry(fail_req)

    reset_resp = service.reset_circuit(ResetCircuitRequest(provider_id="trip-target"))
    assert reset_resp.circuit_state == "CLOSED"

    metrics = service.get_metrics()
    assert metrics.fingerprint_inspections_total == 2
    assert metrics.silent_swaps_detected_total == 2
    assert metrics.circuit_trips_total == 1
