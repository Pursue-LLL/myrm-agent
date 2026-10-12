"""Regression test suite solidifying identity and scope parity across all streaming endpoints.

Directly benchmarks against external reference claw/qm PR #1187 portal-identity-gate.test.ts.
Enforces the 3-state invariant across all enumerated SSE / WebSocket routes:
1. Unauthenticated -> 401 DENIED_UNAUTHENTICATED
2. Scope Mismatch / Unbound Resource -> 403 DENIED
3. Authorized Identity -> 200 ALLOWED
"""

from __future__ import annotations

import pytest

from app.schemas.streaming_gate import (
    EvaluateStreamingAccessRequest,
    StreamingClientIdentityDto,
)
from app.services.security.streaming_gate_service import (
    StreamingGateService,
)

ENUMERATED_STREAMING_ROUTES: list[tuple[str, str, str | None]] = [
    ("/api/v1/agents/general_agent/streaming", "chat:stream", "chat_sess_1"),
    ("/api/v1/tasks/stream", "tasks:stream", "task_001"),
    ("/api/v1/events/notifications/stream", "notifications:stream", "notif_001"),
    ("/api/v1/eval/stream", "eval:stream", "eval_run_1"),
    ("/api/v1/eval/matrix/stream", "eval:stream", "eval_matrix_1"),
    ("/api/v1/wiki/ingest_stream", "wiki:stream", "wiki_doc_1"),
    ("/api/v1/workspace/stream", "workspace:stream", "workspace_1"),
]


@pytest.fixture
def service() -> StreamingGateService:
    return StreamingGateService()


@pytest.mark.parametrize("route_path,required_scope,sample_resource_id", ENUMERATED_STREAMING_ROUTES)
def test_unauthenticated_request_rejected(
    service: StreamingGateService,
    route_path: str,
    required_scope: str,
    sample_resource_id: str | None,
) -> None:
    """Invariant 1: Unauthenticated streaming connection must be rejected with 401."""
    req = EvaluateStreamingAccessRequest(
        endpoint_path=route_path,
        client_identity=StreamingClientIdentityDto(
            subject_id=None,
            auth_source=None,
        ),
        requested_resource_id=sample_resource_id,
    )
    res = service.evaluate_access(req)
    assert res.allowed is False
    assert res.verdict.decision == "DENIED_UNAUTHENTICATED"
    assert res.verdict.status_code == 401


@pytest.mark.parametrize("route_path,required_scope,sample_resource_id", ENUMERATED_STREAMING_ROUTES)
def test_scope_mismatch_request_rejected(
    service: StreamingGateService,
    route_path: str,
    required_scope: str,
    sample_resource_id: str | None,
) -> None:
    """Invariant 2A: Identity lacking the endpoint's specific required scope must be rejected with 403."""
    req = EvaluateStreamingAccessRequest(
        endpoint_path=route_path,
        client_identity=StreamingClientIdentityDto(
            subject_id="valid_user",
            auth_source="bearer",
            granted_scopes=["unrelated:readonly_scope"],
        ),
        requested_resource_id=sample_resource_id,
    )
    res = service.evaluate_access(req)
    assert res.allowed is False
    assert res.verdict.decision == "DENIED_SCOPE_MISMATCH"
    assert res.verdict.status_code == 403


@pytest.mark.parametrize("route_path,required_scope,sample_resource_id", ENUMERATED_STREAMING_ROUTES)
def test_unbound_resource_request_rejected(
    service: StreamingGateService,
    route_path: str,
    required_scope: str,
    sample_resource_id: str | None,
) -> None:
    """Invariant 2B: Token scoped to a specific resource cannot subscribe to other resources."""
    req = EvaluateStreamingAccessRequest(
        endpoint_path=route_path,
        client_identity=StreamingClientIdentityDto(
            subject_id="paired_client",
            auth_source="pair_token",
            granted_scopes=[required_scope],
            bound_resource_ids=["strictly_different_resource_id_999"],
        ),
        requested_resource_id=sample_resource_id,
    )
    res = service.evaluate_access(req)
    assert res.allowed is False
    assert res.verdict.decision == "DENIED_RESOURCE_UNBOUND"
    assert res.verdict.status_code == 403


@pytest.mark.parametrize("route_path,required_scope,sample_resource_id", ENUMERATED_STREAMING_ROUTES)
def test_authorized_request_granted(
    service: StreamingGateService,
    route_path: str,
    required_scope: str,
    sample_resource_id: str | None,
) -> None:
    """Invariant 3: Properly authenticated client with matching scope and binding must be granted access."""
    bound_ids = [sample_resource_id] if sample_resource_id else []
    req = EvaluateStreamingAccessRequest(
        endpoint_path=route_path,
        client_identity=StreamingClientIdentityDto(
            subject_id="authorized_operator",
            auth_source="bearer",
            granted_scopes=[required_scope],
            bound_resource_ids=bound_ids,
        ),
        requested_resource_id=sample_resource_id,
    )
    res = service.evaluate_access(req)
    assert res.allowed is True
    assert res.verdict.decision == "ALLOWED"
    assert res.verdict.status_code == 200
