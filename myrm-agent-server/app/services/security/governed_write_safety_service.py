"""
[POS] app/services/security/governed_write_safety_service.py
[INPUT] app.schemas.governed_write_safety, myrm_agent_harness.core.security.governed_write_safety
[OUTPUT] GovernedWriteSafetyService, get_governed_write_safety_service
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from myrm_agent_harness.core.security.governed_write_safety import (
    CommitWriteResult,
    ConflictRecoveryBundle,
    GovernedWriteProposal,
    GovernedWriteSafetyFacade,
    PreImageSnapshot,
)

from app.schemas.governed_write_safety import (
    ApproveEditRequestDTO,
    ApproveEditResponseDTO,
    CommitEditRequestDTO,
    CommitWriteResultDTO,
    ConflictRecoveryBundleDTO,
    GovernedWriteProposalDTO,
    PreImageSnapshotDTO,
    ProposeEditRequestDTO,
    RegisterOpaqueFileRequestDTO,
    RegisterOpaqueFileResponseDTO,
)

logger = logging.getLogger(__name__)


class GovernedWriteSafetyService:
    """Service mediating opaque file reference governance, edit proposals, and atomic writes."""

    def __init__(
        self,
        facade: GovernedWriteSafetyFacade | None = None,
    ) -> None:
        self._facade = facade or GovernedWriteSafetyFacade()

    @staticmethod
    def _to_proposal_dto(p: GovernedWriteProposal) -> GovernedWriteProposalDTO:
        return GovernedWriteProposalDTO(
            proposal_id=p.proposal_id,
            opaque_file_id=p.opaque_file_id,
            raw_path=p.raw_path,
            base_content_hash=p.base_content_hash,
            candidate_content_hash=p.candidate_content_hash,
            candidate_content=p.candidate_content,
            status=p.status.value,
            lease_token=p.lease_token,
            created_at=p.created_at,
        )

    @staticmethod
    def _to_snapshot_dto(s: PreImageSnapshot | None) -> PreImageSnapshotDTO | None:
        if s is None:
            return None
        return PreImageSnapshotDTO(
            snapshot_id=s.snapshot_id,
            opaque_file_id=s.opaque_file_id,
            raw_path=s.raw_path,
            content_sha256=s.content_sha256,
            timestamp=s.timestamp,
            content_preview=s.content_preview,
        )

    @staticmethod
    def _to_conflict_dto(
        c: ConflictRecoveryBundle | None,
    ) -> ConflictRecoveryBundleDTO | None:
        if c is None:
            return None
        return ConflictRecoveryBundleDTO(
            proposal_id=c.proposal_id,
            opaque_file_id=c.opaque_file_id,
            expected_base_hash=c.expected_base_hash,
            actual_disk_hash=c.actual_disk_hash,
            reason=c.reason,
            suggested_action=c.suggested_action,
        )

    @staticmethod
    def _to_commit_result_dto(r: CommitWriteResult) -> CommitWriteResultDTO:
        return CommitWriteResultDTO(
            success=r.success,
            proposal_id=r.proposal_id,
            status=r.status.value,
            pre_image_snapshot_id=r.pre_image_snapshot_id,
            verified_disk_hash=r.verified_disk_hash,
            error_message=r.error_message,
            conflict_bundle=GovernedWriteSafetyService._to_conflict_dto(r.conflict_bundle),
        )

    def register_opaque_file(
        self, request: RegisterOpaqueFileRequestDTO
    ) -> RegisterOpaqueFileResponseDTO:
        """Shield raw filesystem path behind an opaque token."""
        opaque_id = self._facade.register_opaque_file(request.raw_path)
        logger.info(
            "Registered opaque file '%s' for raw path '%s'",
            opaque_id,
            request.raw_path,
        )
        return RegisterOpaqueFileResponseDTO(
            opaque_file_id=opaque_id,
            raw_path=request.raw_path,
        )

    def resolve_path(self, opaque_file_id: str) -> str | None:
        """Resolve opaque token to physical path."""
        return self._facade.resolve_path(opaque_file_id)

    def propose_edit(self, request: ProposeEditRequestDTO) -> GovernedWriteProposalDTO:
        """Create a binding edit proposal tied to base content pre-image and opaque ID."""
        proposal = self._facade.propose_edit(
            opaque_file_id=request.opaque_file_id,
            current_disk_content=request.current_disk_content,
            candidate_content=request.candidate_content,
        )
        return self._to_proposal_dto(proposal)

    def approve_edit(self, request: ApproveEditRequestDTO) -> ApproveEditResponseDTO:
        """Approve proposal and issue single-use write lease token."""
        lease_token = self._facade.approve_edit(request.proposal_id)
        return ApproveEditResponseDTO(
            proposal_id=request.proposal_id,
            lease_token=lease_token,
        )

    def commit_edit(
        self,
        request: CommitEditRequestDTO,
        write_executor: Callable[[str], str] | None = None,
    ) -> CommitWriteResultDTO:
        """Commit an approved write proposal with atomic stale check and pre-image capture."""
        executor = write_executor if write_executor is not None else (lambda content: content)
        result = self._facade.commit_edit(
            proposal_id=request.proposal_id,
            lease_token=request.lease_token,
            current_disk_content=request.current_disk_content,
            write_executor=executor,
        )
        return self._to_commit_result_dto(result)

    def get_snapshot(self, snapshot_id: str) -> PreImageSnapshotDTO | None:
        """Retrieve pre-image snapshot record."""
        snap = self._facade.get_snapshot(snapshot_id)
        return self._to_snapshot_dto(snap)

    def get_proposal(self, proposal_id: str) -> GovernedWriteProposalDTO | None:
        """Retrieve governed write proposal details."""
        prop = self._facade.get_proposal(proposal_id)
        if prop is None:
            return None
        return self._to_proposal_dto(prop)


_global_service: GovernedWriteSafetyService | None = None


def get_governed_write_safety_service() -> GovernedWriteSafetyService:
    """Dependency provider for GovernedWriteSafetyService."""
    global _global_service
    if _global_service is None:
        _global_service = GovernedWriteSafetyService()
    return _global_service
