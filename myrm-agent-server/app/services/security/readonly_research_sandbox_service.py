"""
[POS] app/services/security/readonly_research_sandbox_service.py
[INPUT] myrm_agent_harness.core.security.readonly_research_sandbox, app.schemas.readonly_research_sandbox
[OUTPUT] ReadOnlyResearchSandboxService, get_readonly_research_sandbox_service

Thread-safe service managing read-only research leases, immutable workspace snapshots,
in-memory Copy-on-Write (CoW) overlays, and real-time security shield badges.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

import threading
from typing import Optional

from myrm_agent_harness.core.security.readonly_research_sandbox import (
    EphemeralCowFileRecord as HarnessFileRecord,
)
from myrm_agent_harness.core.security.readonly_research_sandbox import (
    LeaseStatusEnum as HarnessLeaseStatus,
)
from myrm_agent_harness.core.security.readonly_research_sandbox import (
    ReadOnlyLeaseRecord as HarnessLeaseRecord,
)
from myrm_agent_harness.core.security.readonly_research_sandbox import (
    ReadOnlyResearchSandboxFacade,
)
from myrm_agent_harness.core.security.readonly_research_sandbox import (
    ResearchModeEnum as HarnessModeEnum,
)

from app.schemas.readonly_research_sandbox import (
    EphemeralFileResponse,
    GrantLeaseRequest,
    LeaseStatusEnum,
    PurgeOverlayResponse,
    ReadOnlyLeaseResponse,
    ReadOnlyResearchMetricsResponse,
    ResearchModeEnum,
    RevokeLeaseResponse,
    ShieldBadgeResponse,
    TakeSnapshotRequest,
    ToolEvaluationRequest,
    ToolEvaluationResponse,
    VerifyPurityRequest,
    VerifyPurityResponse,
    WorkspaceSnapshotResponse,
    WriteEphemeralFileRequest,
)


class ReadOnlyResearchSandboxService:
    """Service wrapping read-only research lease and immutable snapshot sandbox operations."""

    def __init__(self, default_ttl_seconds: float = 3600.0) -> None:
        self._lock = threading.RLock()
        self._facade = ReadOnlyResearchSandboxFacade(
            default_ttl_seconds=default_ttl_seconds
        )

    def grant_lease(self, req: GrantLeaseRequest) -> ReadOnlyLeaseResponse:
        """Grant a dynamic read-only research lease to session."""
        mode = HarnessModeEnum(req.research_mode.value)
        custom_tools = (
            tuple(req.custom_allowed_tools) if req.custom_allowed_tools else None
        )
        with self._lock:
            lease = self._facade.grant_research_lease(
                session_id=req.session_id,
                research_mode=mode,
                ttl_seconds=req.ttl_seconds,
                custom_allowed_tools=custom_tools,
            )
        return self._to_lease_response(lease)

    def get_lease(self, session_id: str) -> ReadOnlyLeaseResponse | None:
        """Retrieve active or expired lease for session."""
        with self._lock:
            lease = self._facade.get_lease(session_id)
        if lease is None:
            return None
        return self._to_lease_response(lease)

    def revoke_lease(self, session_id: str) -> RevokeLeaseResponse:
        """Revoke active read-only lease immediately."""
        with self._lock:
            lease = self._facade.revoke_lease(session_id)
        if lease is None:
            return RevokeLeaseResponse(
                session_id=session_id,
                status=LeaseStatusEnum.EXPIRED,
                message="No active lease found to revoke.",
            )
        return RevokeLeaseResponse(
            session_id=session_id,
            status=LeaseStatusEnum(lease.status.value),
            message="Read-only research lease revoked successfully.",
        )

    def evaluate_tool(self, req: ToolEvaluationRequest) -> ToolEvaluationResponse:
        """Evaluate if tool is permissible under active lease."""
        with self._lock:
            allowed, explanation = self._facade.evaluate_tool(
                req.session_id, req.tool_name
            )
            lease = self._facade.get_lease(req.session_id)
            is_enforced = (
                lease is not None and lease.status == HarnessLeaseStatus.ACTIVE
            )

        return ToolEvaluationResponse(
            is_allowed=allowed,
            explanation=explanation,
            session_id=req.session_id,
            is_read_only_enforced=is_enforced,
        )

    def take_snapshot(self, req: TakeSnapshotRequest) -> WorkspaceSnapshotResponse:
        """Capture immutable cryptographic baseline snapshot of protected workspace."""
        files_dict: dict[str, str | bytes] = {k: v for k, v in req.baseline_files.items()}
        with self._lock:
            snap = self._facade.take_snapshot(req.session_id, files_dict)

        return WorkspaceSnapshotResponse(
            snapshot_id=snap.snapshot_id,
            session_id=snap.session_id,
            baseline_timestamp=snap.baseline_timestamp,
            root_digest=snap.root_digest,
            tracked_files_count=len(snap.file_manifest_hashes),
        )

    def write_ephemeral_file(
        self, req: WriteEphemeralFileRequest
    ) -> EphemeralFileResponse:
        """Write transient file into in-memory Copy-on-Write overlay."""
        with self._lock:
            rec = self._facade.write_ephemeral_output(
                session_id=req.session_id,
                virtual_path=req.virtual_path,
                content=req.content,
            )
        return self._to_file_response(rec)

    def list_ephemeral_files(self, session_id: str) -> list[EphemeralFileResponse]:
        """List files currently staged in in-memory CoW overlay."""
        with self._lock:
            records = self._facade.list_ephemeral_outputs(session_id)
        return [self._to_file_response(r) for r in records]

    def purge_overlay(self, session_id: str) -> PurgeOverlayResponse:
        """Purge and destroy in-memory CoW overlay on research task completion."""
        with self._lock:
            purged = self._facade.purge_ephemeral_overlay(session_id)
        return PurgeOverlayResponse(
            session_id=session_id,
            purged_files_count=purged,
            message="Transient CoW overlay purged. Workspace remains 100% pure.",
        )

    def verify_purity(self, req: VerifyPurityRequest) -> VerifyPurityResponse:
        """Verify workspace files against baseline snapshot."""
        files_dict: dict[str, str | bytes] = {k: v for k, v in req.current_files.items()}
        with self._lock:
            is_pure, explanation = self._facade.verify_workspace_purity(
                req.session_id, files_dict
            )
        return VerifyPurityResponse(
            session_id=req.session_id,
            is_pure=is_pure,
            explanation=explanation,
        )

    def get_shield_badge(self, session_id: str) -> ShieldBadgeResponse:
        """Construct real-time UI security indicator badge."""
        with self._lock:
            badge = self._facade.get_shield_badge(session_id)

        return ShieldBadgeResponse(
            is_read_only_active=badge.is_read_only_active,
            active_lease_id=badge.active_lease_id,
            research_mode=ResearchModeEnum(badge.research_mode.value),
            cow_overlay_active=badge.cow_overlay_active,
            workspace_purity_verified=badge.workspace_purity_verified,
            badge_label=badge.badge_label,
        )

    def get_metrics(self) -> ReadOnlyResearchMetricsResponse:
        """Retrieve operational metrics."""
        with self._lock:
            m = self._facade.get_metrics()

        return ReadOnlyResearchMetricsResponse(
            total_leases_granted=m.total_leases_granted,
            active_leases_count=m.active_leases_count,
            leases_revoked_count=m.leases_revoked_count,
            write_attempts_blocked=m.write_attempts_blocked,
            ephemeral_cow_files_staged=m.ephemeral_cow_files_staged,
            overlays_purged_count=m.overlays_purged_count,
            purity_verifications_count=m.purity_verifications_count,
        )

    @staticmethod
    def _to_lease_response(lease_rec: HarnessLeaseRecord) -> ReadOnlyLeaseResponse:
        return ReadOnlyLeaseResponse(
            lease_id=lease_rec.lease_id,
            session_id=lease_rec.session_id,
            research_mode=ResearchModeEnum(lease_rec.research_mode.value),
            granted_at=lease_rec.granted_at,
            expires_at=lease_rec.expires_at,
            status=LeaseStatusEnum(lease_rec.status.value),
            allowed_tools=list(lease_rec.allowed_tools),
            blocked_side_effects=list(lease_rec.blocked_side_effects),
        )

    @staticmethod
    def _to_file_response(f: HarnessFileRecord) -> EphemeralFileResponse:
        return EphemeralFileResponse(
            virtual_path=f.virtual_path,
            sha256_hash=f.sha256_hash,
            written_at=f.written_at,
            size_bytes=len(f.file_bytes),
        )


_SERVICE_INSTANCE: Optional[ReadOnlyResearchSandboxService] = None
_SERVICE_LOCK = threading.RLock()


def get_readonly_research_sandbox_service() -> ReadOnlyResearchSandboxService:
    """Get singleton instance of ReadOnlyResearchSandboxService."""
    global _SERVICE_INSTANCE
    with _SERVICE_LOCK:
        if _SERVICE_INSTANCE is None:
            _SERVICE_INSTANCE = ReadOnlyResearchSandboxService()
        return _SERVICE_INSTANCE
