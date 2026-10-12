"""Unit tests for TracingRedactionService in myrm-agent-server."""

from __future__ import annotations

import pytest

from app.schemas.tracing_redaction import (
    ExecutionPathTypeDto,
    SanitizeTraceSpanRequest,
    TracingOptOutModeDto,
)
from app.services.security.tracing_redaction_service import (
    TracingRedactionService,
    get_tracing_redaction_service,
)


@pytest.fixture
def service() -> TracingRedactionService:
    return TracingRedactionService()


def test_service_sanitize_span_across_execution_paths(
    service: TracingRedactionService,
) -> None:
    request = SanitizeTraceSpanRequest(
        trace_id="srv_trace_01",
        span_id="srv_span_01",
        path_type=ExecutionPathTypeDto.SUCCESS,
        payload={
            "api_key": "sk-proj-123456789012345678901234",
            "password": "mypassword123",
            "safe_metric": 100,
        },
        raw_error="Authentication failure with Bearer abcdef1234567890.xyz",
    )

    response = service.sanitize_span(request)

    assert response.trace_id == "srv_trace_01"
    assert response.span_id == "srv_span_01"
    assert response.path_type == ExecutionPathTypeDto.SUCCESS
    assert response.is_dropped is False
    assert response.redaction_count > 0
    assert response.policy_applied == "redaction_enforced"

    assert response.sanitized_payload["api_key"] == "[REDACTED_SENSITIVE_FIELD]"
    assert response.sanitized_payload["password"] == "[REDACTED_SENSITIVE_FIELD]"
    assert response.sanitized_payload["safe_metric"] == 100
    assert response.sanitized_error is not None
    assert "Bearer [REDACTED_TOKEN]" in response.sanitized_error


def test_service_sanitize_span_drop_trace_opt_out(
    service: TracingRedactionService,
) -> None:
    request = SanitizeTraceSpanRequest(
        trace_id="srv_trace_02",
        span_id="srv_span_02",
        path_type=ExecutionPathTypeDto.ERROR,
        payload={"sensitive_query": "search confidential data"},
        opt_out_requested=True,
        opt_out_mode=TracingOptOutModeDto.DROP_TRACE,
    )

    response = service.sanitize_span(request)

    assert response.is_dropped is True
    assert response.sanitized_payload == {}
    assert response.sanitized_error is None
    assert response.policy_applied == "opt_out_drop"


def test_service_sanitize_span_mandatory_redact_opt_out(
    service: TracingRedactionService,
) -> None:
    request = SanitizeTraceSpanRequest(
        trace_id="srv_trace_03",
        span_id="srv_span_03",
        path_type=ExecutionPathTypeDto.STREAMING,
        payload={"secret": "my-secret-value", "chunk": "hello"},
        opt_out_requested=True,
        opt_out_mode=TracingOptOutModeDto.REDACT_MANDATORY,
    )

    response = service.sanitize_span(request)

    assert response.is_dropped is False
    assert response.sanitized_payload["secret"] == "[REDACTED_SENSITIVE_FIELD]"
    assert response.sanitized_payload["chunk"] == "hello"


def test_get_tracing_redaction_service_dependency() -> None:
    svc1 = get_tracing_redaction_service()
    svc2 = get_tracing_redaction_service()
    assert svc1 is svc2
