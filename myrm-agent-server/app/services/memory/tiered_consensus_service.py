"""Business service implementing Tiered Memory Hierarchy & Proposed Consensus Flow (Item 114).

[POS]
app/services/memory/tiered_consensus_service.py

[INPUT]
- app.schemas.tiered_consensus, myrm_agent_harness.toolkits.memory

[OUTPUT]
- TieredConsensusService, get_tiered_consensus_service
"""


from __future__ import annotations

import logging
from functools import lru_cache

from myrm_agent_harness.toolkits.memory import (
    ConsensusAuditLog,
    ConsensusScopeTier,
    ProposalStatus,
    TieredConsensusManager,
    TieredMemoryRecord,
)

from app.schemas.tiered_consensus import (
    ConsensusAuditLogDTO,
    ProposeRecordRequest,
    ReviewProposalRequest,
    RevokeConsensusRequest,
    TieredMemoryRecordDTO,
)

logger = logging.getLogger(__name__)


def _record_to_dto(rec: TieredMemoryRecord) -> TieredMemoryRecordDTO:
    """Map internal domain tiered record to API DTO."""
    return TieredMemoryRecordDTO(
        record_id=rec.record_id,
        scope_tier=rec.scope_tier.value,
        content=rec.content,
        content_fingerprint=rec.content_fingerprint,
        owner_peer_id=rec.owner_peer_id,
        project_id=rec.project_id,
        status=rec.status.value,
        version=rec.version,
        superseded_by=rec.superseded_by,
        rationale=rec.rationale,
        created_at=rec.created_at,
        updated_at=rec.updated_at,
    )


def _audit_to_dto(log: ConsensusAuditLog) -> ConsensusAuditLogDTO:
    """Map internal domain audit log to API DTO."""
    return ConsensusAuditLogDTO(
        audit_id=log.audit_id,
        record_id=log.record_id,
        action=log.action,
        operator_peer_id=log.operator_peer_id,
        reason=log.reason,
        timestamp=log.timestamp,
    )


class TieredConsensusService:
    """Domain service managing memory tiers, proposal workflows, and approval audits."""

    def __init__(self, manager: TieredConsensusManager | None = None) -> None:
        self._manager = manager or TieredConsensusManager()

    @property
    def manager(self) -> TieredConsensusManager:
        return self._manager

    def propose_record(self, request: ProposeRecordRequest) -> TieredMemoryRecordDTO:
        """Create a new tiered record adhering to scoping and proposal governance."""
        try:
            scope_tier = ConsensusScopeTier(request.scope_tier.lower())
        except ValueError:
            scope_tier = ConsensusScopeTier.PERSONAL

        record = self._manager.propose_record(
            scope_tier=scope_tier,
            content=request.content,
            owner_peer_id=request.owner_peer_id,
            project_id=request.project_id,
            rationale=request.rationale,
            auto_approve_personal_project=request.auto_approve_personal_project,
        )
        return _record_to_dto(record)

    def approve_proposal(self, record_id: str, request: ReviewProposalRequest) -> TieredMemoryRecordDTO:
        """Approve a draft proposal into active consensus status."""
        record = self._manager.approve_proposal(
            record_id=record_id,
            approver_peer_id=request.approver_peer_id,
            reason=request.reason,
        )
        return _record_to_dto(record)

    def reject_proposal(self, record_id: str, request: ReviewProposalRequest) -> TieredMemoryRecordDTO:
        """Reject and discard an unverified proposal draft."""
        record = self._manager.reject_proposal(
            record_id=record_id,
            approver_peer_id=request.approver_peer_id,
            reason=request.reason,
        )
        return _record_to_dto(record)

    def revoke_consensus(self, record_id: str, request: RevokeConsensusRequest) -> TieredMemoryRecordDTO:
        """Revoke a previously ratified consensus rule with optional supersession."""
        record = self._manager.revoke_consensus(
            record_id=record_id,
            operator_peer_id=request.operator_peer_id,
            reason=request.reason,
            superseded_by=request.superseded_by,
        )
        return _record_to_dto(record)

    def get_record(self, record_id: str) -> TieredMemoryRecordDTO | None:
        """Retrieve a specific tiered record by identifier."""
        record = self._manager.get_record(record_id)
        if not record:
            return None
        return _record_to_dto(record)

    def query_records(
        self,
        scope_tier: str | None = None,
        status: str | None = None,
        project_id: str | None = None,
        owner_peer_id: str | None = None,
        include_proposed: bool = False,
    ) -> list[TieredMemoryRecordDTO]:
        """Query scoped records with tier filtering and default proposal isolation."""
        tier_enum = ConsensusScopeTier(scope_tier.lower()) if scope_tier else None
        status_enum = ProposalStatus(status.lower()) if status else None

        records = self._manager.query_records(
            scope_tier=tier_enum,
            status=status_enum,
            project_id=project_id,
            owner_peer_id=owner_peer_id,
            include_proposed=include_proposed,
        )
        return [_record_to_dto(r) for r in records]

    def get_audit_trail(self, record_id: str | None = None) -> list[ConsensusAuditLogDTO]:
        """Retrieve immutable consensus audit logs."""
        logs = self._manager.get_audit_trail(record_id)
        return [_audit_to_dto(log) for log in logs]


@lru_cache(maxsize=1)
def get_tiered_consensus_service() -> TieredConsensusService:
    """Provide singleton TieredConsensusService instance."""
    return TieredConsensusService()
