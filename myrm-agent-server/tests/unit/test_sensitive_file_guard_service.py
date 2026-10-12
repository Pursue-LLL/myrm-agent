"""Unit tests for SensitiveFileGuardService."""

from __future__ import annotations

from app.schemas.sensitive_file_guard import (
    InspectFileOperationRequest,
    IssueUnlockGrantRequest,
)
from app.services.security.sensitive_file_guard_service import (
    SensitiveFileGuardService,
)


def test_service_inspect_blocked_sensitive_file() -> None:
    service = SensitiveFileGuardService()
    req = InspectFileOperationRequest(
        target_path="/workspace/.env",
        operation_type="overwrite",
        tool_name="write_file",
        session_id="unit-sess-vault-1",
    )
    resp = service.inspect_file_operation(req)
    assert resp.allowed is False
    assert resp.category == "env_secret"
    assert resp.matched_rule_id == "env_files"
    assert resp.is_unlocked is False
    assert "strictly denied" in resp.reason

    alerts = service.get_alerts("unit-sess-vault-1")
    assert len(alerts) == 1
    assert alerts[0].category == "env_secret"


def test_service_inspect_allowed_safe_file() -> None:
    service = SensitiveFileGuardService()
    req = InspectFileOperationRequest(
        target_path="src/components/Header.tsx",
        operation_type="write",
        tool_name="write_file",
        session_id="unit-sess-safe",
    )
    resp = service.inspect_file_operation(req)
    assert resp.allowed is True
    assert resp.matched_rule_id is None
    assert resp.category is None


def test_service_unlock_and_revoke_workflow() -> None:
    service = SensitiveFileGuardService()
    target_path = "/workspace/.env.local"

    # 1. Blocked initially
    req_blocked = InspectFileOperationRequest(
        target_path=target_path,
        operation_type="replace",
    )
    assert service.inspect_file_operation(req_blocked).allowed is False

    # 2. Issue unlock grant
    grant_req = IssueUnlockGrantRequest(
        target_path=target_path,
        ttl_seconds=180,
        granted_by="test_user_dialog",
    )
    grant_resp = service.issue_unlock_grant(grant_req)
    assert grant_resp.unlock_token is not None

    # 3. Write with token succeeds
    req_unlocked = InspectFileOperationRequest(
        target_path=target_path,
        operation_type="replace",
        unlock_token=grant_resp.unlock_token,
    )
    decision = service.inspect_file_operation(req_unlocked)
    assert decision.allowed is True
    assert decision.is_unlocked is True

    # 4. Check active grants list
    grants = service.list_active_grants()
    assert any(g.unlock_token == grant_resp.unlock_token for g in grants)

    # 5. Revoke token
    assert service.revoke_unlock_grant(grant_resp.unlock_token) is True
    assert service.inspect_file_operation(req_unlocked).allowed is False
