"""
[POS] app/services/security/host_execution_guard_service.py
[INPUT] myrm_agent_harness.core.security.host_execution_guard, app.schemas.host_execution_guard
[OUTPUT] HostExecutionGuardService, get_host_execution_guard_service

Domain service mediating requests for Local Host Safe Execution Sandbox & Non-Destructive Guardrail.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from myrm_agent_harness.core.security.host_execution_guard import (
    CommandInspectionResult,
    HostExecutionGuardSuite,
    PathAccessMode,
    WorkspaceSnapshot,
)

from app.schemas.host_execution_guard import (
    ApproveCommandRequest,
    CreateSnapshotRequest,
    DestructiveRiskLevelResponse,
    FileSnapshotEntryResponse,
    HostExecutionGuardMetricsResponse,
    InspectCommandRequest,
    InspectCommandResponse,
    InspectPathRequest,
    InspectPathResponse,
    PathProtectionActionResponse,
    RejectCommandRequest,
    RollbackSnapshotRequest,
    WorkspaceSnapshotResponse,
)


class HostExecutionGuardService:
    """Service orchestrating host path shielding, command AST safety, and COW undo snapshots."""

    def __init__(self, suite: HostExecutionGuardSuite | None = None) -> None:
        self._suite = suite or HostExecutionGuardSuite()

    def inspect_path(self, req: InspectPathRequest) -> InspectPathResponse:
        """Inspect target path against system protection rules and determine redirection."""
        mode = PathAccessMode(req.mode.value)
        res = self._suite.inspect_path(target_path=req.target_path, mode=mode)
        return InspectPathResponse(
            original_path=res.original_path,
            is_protected=res.is_protected,
            action=PathProtectionActionResponse(res.action.value),
            effective_path=res.effective_path,
            explanation=res.explanation,
        )

    def inspect_command(self, req: InspectCommandRequest) -> InspectCommandResponse:
        """Inspect shell command string for destructive or hazardous execution patterns."""
        res = self._suite.inspect_command(command=req.command)
        return self._to_command_response(res)

    def approve_command(self, req: ApproveCommandRequest) -> InspectCommandResponse:
        """User confirms and approves a pending high-risk command execution ticket."""
        res = self._suite.approve_command(inspection_id=req.inspection_id)
        return self._to_command_response(res)

    def reject_command(self, req: RejectCommandRequest) -> InspectCommandResponse:
        """User explicitly rejects a pending high-risk command ticket."""
        res = self._suite.reject_command(inspection_id=req.inspection_id)
        return self._to_command_response(res)

    def list_pending_commands(self) -> list[InspectCommandResponse]:
        """List all commands currently awaiting operator approval."""
        pending = self._suite.list_pending_commands()
        return [self._to_command_response(c) for c in pending]

    def create_snapshot(self, req: CreateSnapshotRequest) -> WorkspaceSnapshotResponse:
        """Capture pre-modification state of specified files within the workspace root."""
        snap = self._suite.create_workspace_snapshot(
            workspace_root=req.workspace_root,
            target_rel_paths=tuple(req.target_rel_paths),
            description=req.description,
        )
        return self._to_snapshot_response(snap)

    def rollback_snapshot(self, req: RollbackSnapshotRequest) -> WorkspaceSnapshotResponse:
        """Atomically restore workspace files to the recorded snapshot state."""
        snap = self._suite.rollback_workspace_snapshot(snapshot_id=req.snapshot_id)
        return self._to_snapshot_response(snap)

    def get_snapshot(self, snapshot_id: str) -> WorkspaceSnapshotResponse:
        """Fetch snapshot descriptor by ID."""
        snap = self._suite.get_snapshot(snapshot_id=snapshot_id)
        return self._to_snapshot_response(snap)

    def list_snapshots(self) -> list[WorkspaceSnapshotResponse]:
        """List all tracked workspace snapshots."""
        return [self._to_snapshot_response(s) for s in self._suite.list_snapshots()]

    def get_metrics(self) -> HostExecutionGuardMetricsResponse:
        """Fetch cumulative operational metrics."""
        m = self._suite.metrics
        return HostExecutionGuardMetricsResponse(
            paths_inspected_total=m.paths_inspected_total,
            paths_redirected_total=m.paths_redirected_total,
            paths_blocked_total=m.paths_blocked_total,
            commands_inspected_total=m.commands_inspected_total,
            commands_blocked_total=m.commands_blocked_total,
            hitl_requested_total=m.hitl_requested_total,
            hitl_approved_total=m.hitl_approved_total,
            snapshots_created_total=m.snapshots_created_total,
            rollbacks_executed_total=m.rollbacks_executed_total,
        )

    @staticmethod
    def _to_command_response(res: CommandInspectionResult) -> InspectCommandResponse:
        return InspectCommandResponse(
            inspection_id=res.inspection_id,
            command=res.command,
            risk_level=DestructiveRiskLevelResponse(res.risk_level.value),
            matched_patterns=list(res.matched_patterns),
            explanation=res.explanation,
            requires_hitl=res.requires_hitl,
            is_blocked=res.is_blocked,
        )

    @staticmethod
    def _to_snapshot_response(snap: WorkspaceSnapshot) -> WorkspaceSnapshotResponse:
        entries_resp = [
            FileSnapshotEntryResponse(
                relative_path=e.relative_path,
                original_hash=e.original_hash,
                original_content=e.original_content,
                is_deleted=e.is_deleted,
            )
            for e in snap.entries
        ]
        return WorkspaceSnapshotResponse(
            snapshot_id=snap.snapshot_id,
            workspace_root=snap.workspace_root,
            created_at=snap.created_at,
            entries=entries_resp,
            description=snap.description,
            is_restored=snap.is_restored,
        )


_default_service: HostExecutionGuardService | None = None


def get_host_execution_guard_service() -> HostExecutionGuardService:
    """Dependency injection provider for HostExecutionGuardService."""
    global _default_service
    if _default_service is None:
        _default_service = HostExecutionGuardService()
    return _default_service
