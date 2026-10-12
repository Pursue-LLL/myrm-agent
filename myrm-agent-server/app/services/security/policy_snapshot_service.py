"""Policy Snapshot Service.

[INPUT]
- BindTaskPolicyRequest, SoftUpdatePolicyRequest, EmergencyHotKillRequest,
  RevokeEmergencyHotKillRequest, AssertToolExecutionRequest.

[OUTPUT]
- ExecutionPolicySnapshotDto, EmergencyHotKillDirectiveDto, AssertToolExecutionResponse.

[POS]
- Server security service. Wraps harness PolicySnapshotManager to enforce in-flight
  policy snapshot pinning and dual-track update channels.
"""

from __future__ import annotations

import logging

from myrm_agent_harness.core.security.policy_snapshot import (
    EmergencyHotKillBlockedError,
    EmergencyHotKillDirective,
    ExecutionPolicySnapshot,
    PolicyDriftViolationError,
    PolicySnapshotManager,
)

from app.schemas.policy_snapshot import (
    AssertToolExecutionResponse,
    EmergencyHotKillDirectiveDto,
    EmergencyHotKillRequest,
    ExecutionPolicySnapshotDto,
    SoftUpdatePolicyRequest,
)

logger = logging.getLogger(__name__)


def _snapshot_to_dto(snapshot: ExecutionPolicySnapshot) -> ExecutionPolicySnapshotDto:
    """Convert harness ExecutionPolicySnapshot into Pydantic DTO."""
    return ExecutionPolicySnapshotDto(
        snapshot_id=snapshot.snapshot_id,
        version_number=snapshot.version_number,
        policy_snapshot_hash=snapshot.policy_snapshot_hash,
        prompt_template_hash=snapshot.prompt_template_hash,
        allowed_tools=list(snapshot.allowed_tools),
        governance_rules=dict(snapshot.governance_rules),
        created_at=snapshot.created_at,
    )


def _directive_to_dto(directive: EmergencyHotKillDirective) -> EmergencyHotKillDirectiveDto:
    """Convert harness EmergencyHotKillDirective into Pydantic DTO."""
    return EmergencyHotKillDirectiveDto(
        directive_id=directive.directive_id,
        revoked_tools=list(directive.revoked_tools),
        reason=directive.reason,
        issued_at=directive.issued_at,
        is_active=directive.is_active,
    )


class PolicySnapshotService:
    """Service managing execution policy snapshots, pinning, and dual-track updates."""

    def __init__(self) -> None:
        self._manager = PolicySnapshotManager(
            initial_prompt_template="Standard System Prompt",
            initial_allowed_tools=("read_file", "search_web", "list_dir"),
            initial_governance_rules={"timeout_seconds": 60, "max_iterations": 25},
        )

    @property
    def manager(self) -> PolicySnapshotManager:
        """Underlying harness PolicySnapshotManager instance."""
        return self._manager

    def get_active_snapshot(self) -> ExecutionPolicySnapshotDto:
        """Retrieve currently active snapshot for new tasks."""
        return _snapshot_to_dto(self._manager.active_snapshot)

    def bind_task_policy(self, task_id: str) -> ExecutionPolicySnapshotDto:
        """Pin active snapshot to a newly initiated task."""
        snapshot = self._manager.bind_task_policy(task_id)
        return _snapshot_to_dto(snapshot)

    def get_task_policy(self, task_id: str) -> ExecutionPolicySnapshotDto | None:
        """Retrieve the pinned snapshot for an in-flight task."""
        snapshot = self._manager.get_task_policy(task_id)
        return _snapshot_to_dto(snapshot) if snapshot is not None else None

    def apply_soft_update(self, req: SoftUpdatePolicyRequest) -> ExecutionPolicySnapshotDto:
        """Track A: Apply soft update for subsequent tasks, preserving in-flight tasks."""
        snapshot = self._manager.apply_soft_update(
            new_prompt_template=req.prompt_template,
            new_allowed_tools=req.allowed_tools,
            new_governance_rules=req.governance_rules,
        )
        return _snapshot_to_dto(snapshot)

    def apply_emergency_hot_kill(
        self, req: EmergencyHotKillRequest
    ) -> EmergencyHotKillDirectiveDto:
        """Track B: Apply emergency hot-kill immediately intercepting in-flight tasks."""
        directive = self._manager.apply_emergency_hot_kill(
            revoked_tools=req.revoked_tools,
            reason=req.reason,
        )
        return _directive_to_dto(directive)

    def revoke_emergency_hot_kill(self, directive_id: str) -> bool:
        """Revoke an active emergency directive."""
        return self._manager.revoke_emergency_hot_kill(directive_id)

    def assert_tool_execution(self, task_id: str, tool_name: str) -> AssertToolExecutionResponse:
        """Assert whether a tool call is permitted for an in-flight task."""
        snapshot = self._manager.get_task_policy(task_id)
        if snapshot is None:
            snapshot = self._manager.bind_task_policy(task_id)

        try:
            self._manager.assert_tool_execution_allowed(task_id=task_id, tool_name=tool_name)
            return AssertToolExecutionResponse(
                allowed=True,
                task_id=task_id,
                tool_name=tool_name,
                snapshot_version=snapshot.version_number,
                snapshot_hash=snapshot.policy_snapshot_hash,
                blocked_reason=None,
            )
        except (EmergencyHotKillBlockedError, PolicyDriftViolationError) as exc:
            return AssertToolExecutionResponse(
                allowed=False,
                task_id=task_id,
                tool_name=tool_name,
                snapshot_version=snapshot.version_number,
                snapshot_hash=snapshot.policy_snapshot_hash,
                blocked_reason=str(exc),
            )


_service_instance: PolicySnapshotService | None = None


def get_policy_snapshot_service() -> PolicySnapshotService:
    """Obtain or initialize the singleton PolicySnapshotService instance."""
    global _service_instance
    if _service_instance is None:
        _service_instance = PolicySnapshotService()
    return _service_instance
