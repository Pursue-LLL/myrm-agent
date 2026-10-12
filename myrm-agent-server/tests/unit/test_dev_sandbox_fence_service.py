"""Unit tests for DevSandboxFenceService."""

from __future__ import annotations

from app.schemas.dev_sandbox_fence import (
    InspectDevOperationRequest,
    RegisterSyntheticFixtureRequest,
)
from app.services.security.dev_sandbox_fence_service import DevSandboxFenceService


def test_service_inspect_sql_mutations_blocked() -> None:
    service = DevSandboxFenceService()
    req = InspectDevOperationRequest(
        operation_type="sql",
        target="records",
        payload="UPDATE records SET status = 'approved' WHERE id = 1",
        session_id="unit-sess-sql",
    )
    resp = service.inspect_operation(req)
    assert resp.allowed is False
    assert resp.violation_type == "prod_db_write_blocked"
    assert "strictly prohibited" in resp.reason

    alerts = service.get_alerts("unit-sess-sql")
    assert len(alerts) == 1
    assert alerts[0].violation_type == "prod_db_write_blocked"


def test_service_inspect_sql_read_allowed() -> None:
    service = DevSandboxFenceService()
    req = InspectDevOperationRequest(
        operation_type="sql",
        target="records",
        payload="SELECT * FROM records WHERE id = 1",
        session_id="unit-sess-read",
    )
    resp = service.inspect_operation(req)
    assert resp.allowed is True
    assert resp.violation_type is None


def test_service_inspect_git_branch() -> None:
    service = DevSandboxFenceService()

    # Blocked production branch
    req_bad = InspectDevOperationRequest(
        operation_type="git_branch",
        target="main",
    )
    resp_bad = service.inspect_operation(req_bad)
    assert resp_bad.allowed is False
    assert resp_bad.violation_type == "prod_branch_push_blocked"

    # Allowed dev branch
    req_good = InspectDevOperationRequest(
        operation_type="git_branch",
        target="agent/dev-patch-123",
    )
    resp_good = service.inspect_operation(req_good)
    assert resp_good.allowed is True
    assert resp_good.violation_type is None


def test_service_synthetic_fixture_substitution() -> None:
    service = DevSandboxFenceService()
    req = InspectDevOperationRequest(
        operation_type="db_connect",
        target="postgresql://prod-db.internal:5432/patients",
    )
    resp = service.inspect_operation(req)
    assert resp.allowed is True
    assert resp.violation_type == "prod_credential_substitution"
    assert "mock://" in (resp.substituted_target or "")


def test_service_fixture_management() -> None:
    service = DevSandboxFenceService()
    reg_req = RegisterSyntheticFixtureRequest(
        fixture_id="custom_analytics_mock",
        database_type="postgres",
        read_only_uri="mock://analytics-mock:5432/readonly",
        sample_count=50,
        description="Masked analytics test dataset",
    )
    created = service.register_fixture(reg_req)
    assert created.fixture_id == "custom_analytics_mock"

    fixtures = service.list_fixtures()
    assert any(f.fixture_id == "custom_analytics_mock" for f in fixtures)

    assert service.unregister_fixture("custom_analytics_mock") is True
    assert not any(f.fixture_id == "custom_analytics_mock" for f in service.list_fixtures())


def test_service_policy_and_mode_switch() -> None:
    service = DevSandboxFenceService()
    policy = service.get_policy()
    assert "main" in policy.blocked_branches
    assert policy.mode == "dev_isolated"

    # Switch to production controlled
    new_mode = service.set_mode("production_controlled")
    assert new_mode == "production_controlled"

    # Mutating SQL is bypassed in production mode
    req = InspectDevOperationRequest(
        operation_type="sql",
        target="users",
        payload="DELETE FROM users WHERE id = 5",
    )
    resp = service.inspect_operation(req)
    assert resp.allowed is True
    assert "bypassed" in resp.reason
