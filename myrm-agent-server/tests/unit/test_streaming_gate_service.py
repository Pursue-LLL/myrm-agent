"""Unit tests for StreamingGateService."""

from __future__ import annotations

import pytest

from app.schemas.streaming_gate import (
    EvaluateStreamingAccessRequest,
    StreamingClientIdentityDto,
    StreamingEndpointContractDto,
)
from app.services.security.streaming_gate_service import StreamingGateService


@pytest.fixture
def sample_service() -> StreamingGateService:
    return StreamingGateService()


def test_list_and_register_contracts(sample_service: StreamingGateService) -> None:
    contracts = sample_service.list_contracts()
    assert len(contracts) >= 7
    # Check default known streaming endpoints are registered
    paths = [c.endpoint_path for c in contracts]
    assert "/api/v1/agents/general_agent/streaming" in paths
    assert "/api/v1/tasks/stream" in paths
    assert "/api/v1/events/notifications/stream" in paths

    # Register custom streaming contract
    sample_service.register_contract(
        StreamingEndpointContractDto(
            endpoint_path="/api/v1/custom/stream",
            transport="SSE",
            requires_auth=True,
            required_scope="custom:stream",
            target_resource_type="custom",
        )
    )
    updated = sample_service.list_contracts()
    assert any(c.endpoint_path == "/api/v1/custom/stream" for c in updated)


def test_evaluate_access_anonymous_denied(sample_service: StreamingGateService) -> None:
    req = EvaluateStreamingAccessRequest(
        endpoint_path="/api/v1/tasks/stream",
        client_identity=StreamingClientIdentityDto(
            subject_id=None,
            auth_source=None,
        ),
    )
    res = sample_service.evaluate_access(req)
    assert res.allowed is False
    assert res.verdict.decision == "DENIED_UNAUTHENTICATED"
    assert res.verdict.status_code == 401


def test_evaluate_access_scope_mismatch(sample_service: StreamingGateService) -> None:
    req = EvaluateStreamingAccessRequest(
        endpoint_path="/api/v1/tasks/stream",
        client_identity=StreamingClientIdentityDto(
            subject_id="user_123",
            auth_source="bearer",
            granted_scopes=["wrong:scope"],
        ),
    )
    res = sample_service.evaluate_access(req)
    assert res.allowed is False
    assert res.verdict.decision == "DENIED_SCOPE_MISMATCH"
    assert res.verdict.status_code == 403


def test_evaluate_access_resource_bound_allowed_and_denied(
    sample_service: StreamingGateService,
) -> None:
    # 1. Allowed on bound resource
    req_allowed = EvaluateStreamingAccessRequest(
        endpoint_path="/api/v1/agents/general_agent/streaming",
        client_identity=StreamingClientIdentityDto(
            subject_id="mobile_pair",
            auth_source="pair_token",
            granted_scopes=["chat:stream"],
            bound_resource_ids=["chat_abc"],
        ),
        requested_resource_id="chat_abc",
    )
    res_allowed = sample_service.evaluate_access(req_allowed)
    assert res_allowed.allowed is True
    assert res_allowed.verdict.decision == "ALLOWED"
    assert res_allowed.verdict.status_code == 200

    # 2. Denied on unbound resource
    req_denied = EvaluateStreamingAccessRequest(
        endpoint_path="/api/v1/agents/general_agent/streaming",
        client_identity=StreamingClientIdentityDto(
            subject_id="mobile_pair",
            auth_source="pair_token",
            granted_scopes=["chat:stream"],
            bound_resource_ids=["chat_abc"],
        ),
        requested_resource_id="chat_different_user",
    )
    res_denied = sample_service.evaluate_access(req_denied)
    assert res_denied.allowed is False
    assert res_denied.verdict.decision == "DENIED_RESOURCE_UNBOUND"
    assert res_denied.verdict.status_code == 403


def test_run_parity_audit_compliant(sample_service: StreamingGateService) -> None:
    audit = sample_service.run_parity_audit()
    assert audit.total_endpoints_evaluated >= 7
    # All default streaming routes enforce auth and explicit scopes
    assert audit.is_compliant is True
    assert audit.total_issues_found == 0
