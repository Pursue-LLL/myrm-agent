"""Service implementation for Immutable Host Containerized Sandbox and Rollback API.

[POS] app/services/security/immutable_sandbox_rollback_service.py
[INPUT] myrm_agent_harness.core.security.immutable_sandbox_rollback, app.schemas.immutable_sandbox_rollback
[OUTPUT] ImmutableSandboxRollbackService, get_immutable_sandbox_rollback_service
"""

from __future__ import annotations

import logging

from myrm_agent_harness.core.security.immutable_sandbox_rollback.immutable_policy import (
    ImmutableSandboxPolicyEngine,
)
from myrm_agent_harness.core.security.immutable_sandbox_rollback.rollback_manager import (
    SandboxAtomicRollbackManager,
)

from app.schemas.immutable_sandbox_rollback import (
    CheckpointResponse,
    CreateCheckpointRequest,
    EvaluateCommandBlastRadiusRequest,
    EvaluateCommandBlastRadiusResponse,
    GetMountSpecRequest,
    GetMountSpecResponse,
    ListCheckpointsResponse,
    RollbackRequest,
    RollbackResponse,
)

logger = logging.getLogger(__name__)


class ImmutableSandboxRollbackService:
    """Business service governing immutable host boundaries and atomic sandbox rollbacks."""

    def __init__(
        self,
        policy_engine: ImmutableSandboxPolicyEngine | None = None,
        rollback_mgr: SandboxAtomicRollbackManager | None = None,
    ) -> None:
        self._policy_engine = policy_engine or ImmutableSandboxPolicyEngine()
        self._rollback_mgr = rollback_mgr or SandboxAtomicRollbackManager()

    def evaluate_command_blast_radius(
        self,
        req: EvaluateCommandBlastRadiusRequest,
    ) -> EvaluateCommandBlastRadiusResponse:
        """Evaluate shell command for potential host system mutation or privilege escalation."""
        assessment = self._policy_engine.assess_command_blast_radius(req.command)
        return EvaluateCommandBlastRadiusResponse(
            command=assessment.command,
            tier=assessment.tier.value,
            blocked=assessment.blocked,
            targeted_immutable_paths=assessment.targeted_immutable_paths,
            mitigation_applied=assessment.mitigation_applied,
        )

    def get_mount_spec(self, req: GetMountSpecRequest) -> GetMountSpecResponse:
        """Generate hardened read-only mount specification and Docker CLI flags."""
        spec = self._policy_engine.generate_mount_spec(workspace_path=req.workspace_path)
        docker_flags = self._policy_engine.generate_docker_flags(spec)
        return GetMountSpecResponse(
            read_only_root=spec.read_only_root,
            read_only_bind_mounts=spec.read_only_bind_mounts,
            writable_workspace_path=spec.writable_workspace_path,
            tmpfs_mounts=spec.tmpfs_mounts,
            drop_all_capabilities=spec.drop_all_capabilities,
            docker_flags=docker_flags,
        )

    def create_checkpoint(self, req: CreateCheckpointRequest) -> CheckpointResponse:
        """Create an atomic snapshot checkpoint for a sandbox workspace."""
        chk = self._rollback_mgr.create_checkpoint(
            sandbox_id=req.sandbox_id,
            description=req.description,
            file_manifest=req.file_manifest,
        )
        return CheckpointResponse(
            checkpoint_id=chk.checkpoint_id,
            sandbox_id=chk.sandbox_id,
            created_at=chk.created_at,
            description=chk.description,
            workspace_state_digest=chk.workspace_state_digest,
            files_count=len(chk.file_manifest),
        )

    def rollback_to_checkpoint(self, req: RollbackRequest) -> RollbackResponse:
        """Execute atomic rollback to a specified checkpoint with zero blast radius."""
        result, restored_manifest = self._rollback_mgr.rollback_to_checkpoint(
            sandbox_id=req.sandbox_id,
            checkpoint_id=req.checkpoint_id,
            current_manifest=req.current_file_manifest,
        )
        return RollbackResponse(
            success=result.success,
            checkpoint_id=result.checkpoint_id,
            restored_files_count=result.restored_files_count,
            pruned_files_count=result.pruned_files_count,
            restored_at=result.restored_at,
            restored_manifest=restored_manifest,
            error_message=result.error_message,
        )

    def list_checkpoints(self, sandbox_id: str) -> ListCheckpointsResponse:
        """List all snapshots registered for a sandbox."""
        checkpoints = self._rollback_mgr.list_checkpoints(sandbox_id)
        responses = [
            CheckpointResponse(
                checkpoint_id=c.checkpoint_id,
                sandbox_id=c.sandbox_id,
                created_at=c.created_at,
                description=c.description,
                workspace_state_digest=c.workspace_state_digest,
                files_count=len(c.file_manifest),
            )
            for c in checkpoints
        ]
        return ListCheckpointsResponse(sandbox_id=sandbox_id, checkpoints=responses)


_service_instance: ImmutableSandboxRollbackService | None = None


def get_immutable_sandbox_rollback_service() -> ImmutableSandboxRollbackService:
    """Singleton getter for ImmutableSandboxRollbackService."""
    global _service_instance
    if _service_instance is None:
        _service_instance = ImmutableSandboxRollbackService()
    return _service_instance
