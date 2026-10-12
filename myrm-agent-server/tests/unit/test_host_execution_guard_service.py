"""
[POS] tests/unit/test_host_execution_guard_service.py
[INPUT] pytest, tmp_path, app.schemas.host_execution_guard, app.services.security.host_execution_guard_service
[OUTPUT] Unit tests for HostExecutionGuardService

Validates service-level host path shielding, command AST safety verification,
and atomic workspace COW snapshotting and rollback.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from pathlib import Path

from myrm_agent_harness.core.security.host_execution_guard import HostExecutionGuardSuite

from app.schemas.host_execution_guard import (
    ApproveCommandRequest,
    CreateSnapshotRequest,
    DestructiveRiskLevelResponse,
    InspectCommandRequest,
    InspectPathRequest,
    PathAccessModeResponse,
    PathProtectionActionResponse,
    RejectCommandRequest,
    RollbackSnapshotRequest,
)
from app.services.security.host_execution_guard_service import (
    HostExecutionGuardService,
)


def test_service_path_inspection_and_overlay(tmp_path: Path) -> None:
    """Validate path inspection with blocking and scratch overlay redirection."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    scratch = tmp_path / "scratch"
    scratch.mkdir()

    suite = HostExecutionGuardSuite(
        workspace_root=str(workspace),
        scratch_overlay_dir=str(scratch),
    )
    service = HostExecutionGuardService(suite=suite)

    # 1. System path with overlay redirects
    res_overlay = service.inspect_path(
        InspectPathRequest(
            target_path="/usr/bin/python3",
            mode=PathAccessModeResponse.WRITE,
        )
    )
    assert res_overlay.is_protected is True
    assert res_overlay.action == PathProtectionActionResponse.VIRTUAL_OVERLAY
    assert str(scratch) in res_overlay.effective_path

    # 2. Credential path blocks directly
    res_cred = service.inspect_path(
        InspectPathRequest(
            target_path="~/.ssh/authorized_keys",
            mode=PathAccessModeResponse.READ,
        )
    )
    assert res_cred.is_protected is True
    assert res_cred.action == PathProtectionActionResponse.BLOCK

    # 3. Workspace file allowed
    ws_file = workspace / "index.js"
    res_ws = service.inspect_path(
        InspectPathRequest(
            target_path=str(ws_file),
            mode=PathAccessModeResponse.WRITE,
        )
    )
    assert res_ws.is_protected is False
    assert res_ws.action == PathProtectionActionResponse.ALLOW


def test_service_command_inspection_and_approval_lifecycle() -> None:
    """Validate destructive command detection and HITL approval/rejection lifecycle."""
    service = HostExecutionGuardService()

    # 1. Catastrophic command
    res_cat = service.inspect_command(
        InspectCommandRequest(command="rm -rf /")
    )
    assert res_cat.risk_level == DestructiveRiskLevelResponse.BLOCKED_DESTRUCTIVE
    assert res_cat.is_blocked is True
    assert res_cat.requires_hitl is False

    # 2. Command requiring HITL
    res_hitl = service.inspect_command(
        InspectCommandRequest(command="rm -rf ./dist")
    )
    assert res_hitl.risk_level == DestructiveRiskLevelResponse.REQUIRE_HITL
    assert res_hitl.requires_hitl is True
    assert res_hitl.is_blocked is False

    # 3. Check pending list
    pending = service.list_pending_commands()
    assert len(pending) == 1
    assert pending[0].inspection_id == res_hitl.inspection_id

    # 4. Approve command
    appr_res = service.approve_command(
        ApproveCommandRequest(inspection_id=res_hitl.inspection_id)
    )
    assert appr_res.risk_level == DestructiveRiskLevelResponse.SAFE
    assert appr_res.is_blocked is False
    assert len(service.list_pending_commands()) == 0

    # 5. Reject another command
    res_hitl2 = service.inspect_command(
        InspectCommandRequest(command="systemctl stop docker")
    )
    rej_res = service.reject_command(
        RejectCommandRequest(inspection_id=res_hitl2.inspection_id)
    )
    assert rej_res.risk_level == DestructiveRiskLevelResponse.BLOCKED_DESTRUCTIVE
    assert rej_res.is_blocked is True


def test_service_workspace_snapshot_and_rollback(tmp_path: Path) -> None:
    """Validate pre-modification snapshot capture and atomic undo."""
    service = HostExecutionGuardService()

    f1 = tmp_path / "config.yaml"
    f1.write_text("port: 8080\n", encoding="utf-8")
    f2_rel = "temp_dump.sql"

    # 1. Capture snapshot
    snap_res = service.create_snapshot(
        CreateSnapshotRequest(
            workspace_root=str(tmp_path),
            target_rel_paths=["config.yaml", f2_rel],
            description="Pre-config edit",
        )
    )
    assert snap_res.is_restored is False
    assert len(snap_res.entries) == 2

    # 2. Modify f1 and create f2
    f1.write_text("port: 9999\n", encoding="utf-8")
    f2 = tmp_path / f2_rel
    f2.write_text("SELECT * FROM users;\n", encoding="utf-8")

    # 3. Execute rollback
    rb_res = service.rollback_snapshot(
        RollbackSnapshotRequest(snapshot_id=snap_res.snapshot_id)
    )
    assert rb_res.is_restored is True

    # 4. Verify original state
    assert f1.read_text(encoding="utf-8") == "port: 8080\n"
    assert not f2.exists()

    # 5. List and get snapshot
    snaps = service.list_snapshots()
    assert any(s.snapshot_id == snap_res.snapshot_id for s in snaps)

    single = service.get_snapshot(snap_res.snapshot_id)
    assert single.snapshot_id == snap_res.snapshot_id


def test_service_metrics() -> None:
    """Validate cumulative metrics reporting."""
    service = HostExecutionGuardService()

    service.inspect_command(InspectCommandRequest(command="git pull"))
    service.inspect_path(
        InspectPathRequest(target_path="/etc/resolv.conf", mode=PathAccessModeResponse.WRITE)
    )

    metrics = service.get_metrics()
    assert metrics.commands_inspected_total >= 1
    assert metrics.paths_inspected_total >= 1
