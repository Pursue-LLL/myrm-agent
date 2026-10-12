"""Unit tests for PolicySnapshotService."""

from __future__ import annotations

from app.schemas.policy_snapshot import (
    EmergencyHotKillRequest,
    SoftUpdatePolicyRequest,
)
from app.services.security.policy_snapshot_service import PolicySnapshotService


def test_policy_snapshot_service_pinning_and_dual_track() -> None:
    service = PolicySnapshotService()

    # 1. Initial snapshot check
    active = service.get_active_snapshot()
    assert active.version_number == 1
    assert "read_file" in active.allowed_tools

    # 2. Pin task-A
    snap_a = service.bind_task_policy("task-A")
    assert snap_a.version_number == 1

    # Allowed tool executes
    res_a1 = service.assert_tool_execution("task-A", "read_file")
    assert res_a1.allowed is True
    assert res_a1.snapshot_version == 1

    # 3. Track A: Soft Update
    snap_v2 = service.apply_soft_update(
        SoftUpdatePolicyRequest(
            prompt_template="System Prompt v2",
            allowed_tools=["read_file", "search_web", "new_api_tool"],
            governance_rules={"timeout_seconds": 120},
        )
    )
    assert snap_v2.version_number == 2
    assert service.get_active_snapshot().version_number == 2

    # In-flight task-A is still pinned to v1; calling new_api_tool is blocked
    res_a2 = service.assert_tool_execution("task-A", "new_api_tool")
    assert res_a2.allowed is False
    assert "not permitted by pinned policy snapshot" in (res_a2.blocked_reason or "")

    # Newly initiated task-B binds to v2 and is allowed to call new_api_tool
    service.bind_task_policy("task-B")
    res_b = service.assert_tool_execution("task-B", "new_api_tool")
    assert res_b.allowed is True
    assert res_b.snapshot_version == 2


def test_emergency_hot_kill_and_revocation() -> None:
    service = PolicySnapshotService()
    service.bind_task_policy("task-C")

    # read_file allowed initially
    res_init = service.assert_tool_execution("task-C", "read_file")
    assert res_init.allowed is True

    # Track B: Emergency Hot Kill
    hot_kill = service.apply_emergency_hot_kill(
        EmergencyHotKillRequest(
            revoked_tools=["read_file"],
            reason="Zero-day path traversal vulnerability reported",
        )
    )
    assert hot_kill.is_active is True

    # Immediate interception for in-flight task-C
    res_blocked = service.assert_tool_execution("task-C", "read_file")
    assert res_blocked.allowed is False
    assert "blocked by active emergency hot-kill" in (res_blocked.blocked_reason or "")

    # Revoke hot kill
    revoked = service.revoke_emergency_hot_kill(hot_kill.directive_id)
    assert revoked is True

    # Access restored
    res_restored = service.assert_tool_execution("task-C", "read_file")
    assert res_restored.allowed is True
