"""Service layer for Multi-Human Multi-Agent Live Document Co-Authoring Ledger."""

import time
from typing import Dict, List, Optional, Tuple

from myrm_agent_harness.agent.sub_agents.coauthoring_ledger import (
    ArbitrationStrategy,
    BlockType,
    CoAuthoringConflictArbitrator,
    CollaboratorProfile,
    CollaboratorType,
    ConflictRecord,
    DeltaEntry,
    DeltaOperation,
    DocumentBlock,
    LiveDocumentCoAuthoringLedger,
    StagingProposal,
)

from app.schemas.coauthoring_ledger import (
    AcquireLeaseRequest,
    ApplyDeltaRequest,
    ArbitrateConflictRequest,
    ArbitrationStrategyEnum,
    ArbitrationVerdictDTO,
    BlockTypeEnum,
    CollaboratorProfileDTO,
    CollaboratorTypeEnum,
    ConflictRecordDTO,
    DeltaEntryDTO,
    DeltaOperationEnum,
    DocumentBlockDTO,
    InitDocumentRequest,
    RegisterCollaboratorRequest,
    ReleaseLeaseRequest,
    StagingProposalDTO,
)


class CoAuthoringLedgerService:
    """Session-isolated service managing live collaborative document ledgers and conflict arbitration."""

    def __init__(self) -> None:
        self._ledgers: Dict[str, LiveDocumentCoAuthoringLedger] = {}
        self._arbitrators: Dict[str, CoAuthoringConflictArbitrator] = {}

    def _get_bundle(self, chat_id: str) -> Tuple[LiveDocumentCoAuthoringLedger, CoAuthoringConflictArbitrator]:
        if chat_id not in self._ledgers:
            ledger = LiveDocumentCoAuthoringLedger(
                document_id=f"doc-{chat_id}",
                title=f"Collaborative Doc ({chat_id})",
            )
            arbitrator = CoAuthoringConflictArbitrator(ledger)
            self._ledgers[chat_id] = ledger
            self._arbitrators[chat_id] = arbitrator
        return self._ledgers[chat_id], self._arbitrators[chat_id]

    def _to_block_dto(self, block: DocumentBlock) -> DocumentBlockDTO:
        return DocumentBlockDTO(
            block_id=block.block_id,
            block_type=BlockTypeEnum(block.block_type.value),
            content=block.content,
            version=block.version,
            last_author_id=block.last_author_id,
            last_updated_at=block.last_updated_at,
            lease_holder_id=block.lease_holder_id,
            lease_expires_at=block.lease_expires_at,
        )

    def _to_delta_dto(self, delta: DeltaEntry) -> DeltaEntryDTO:
        return DeltaEntryDTO(
            delta_id=delta.delta_id,
            document_id=delta.document_id,
            block_id=delta.block_id,
            operation=DeltaOperationEnum(delta.operation.value),
            author_id=delta.author_id,
            author_type=CollaboratorTypeEnum(delta.author_type.value),
            principal_human_id=delta.principal_human_id,
            prev_content=delta.prev_content,
            new_content=delta.new_content,
            intent_reason=delta.intent_reason,
            timestamp=delta.timestamp,
            applied=delta.applied,
        )

    def _to_proposal_dto(self, prop: StagingProposal) -> StagingProposalDTO:
        return StagingProposalDTO(
            proposal_id=prop.proposal_id,
            block_id=prop.block_id,
            author_id=prop.author_id,
            content=prop.content,
            intent_reason=prop.intent_reason,
            status=prop.status,
            created_at=prop.created_at,
        )

    def _to_conflict_dto(self, record: ConflictRecord) -> ConflictRecordDTO:
        return ConflictRecordDTO(
            conflict_id=record.conflict_id,
            block_id=record.block_id,
            competing_authors=list(record.competing_authors),
            detected_at=record.detected_at,
            resolved=record.resolved,
            resolution_strategy=ArbitrationStrategyEnum(record.resolution_strategy.value),
            resolution_summary=record.resolution_summary,
        )

    def register_collaborator(
        self, chat_id: str, req: RegisterCollaboratorRequest
    ) -> CollaboratorProfileDTO:
        ledger, _ = self._get_bundle(chat_id)
        now = time.time()
        profile = CollaboratorProfile(
            collaborator_id=req.collaborator_id,
            collaborator_type=CollaboratorType(req.collaborator_type.value),
            name=req.name,
            principal_human_id=req.principal_human_id,
            role_description=req.role_description,
            joined_at=now,
        )
        ledger.register_collaborator(profile)
        return CollaboratorProfileDTO(
            collaborator_id=profile.collaborator_id,
            collaborator_type=CollaboratorTypeEnum(profile.collaborator_type.value),
            name=profile.name,
            principal_human_id=profile.principal_human_id,
            role_description=profile.role_description,
            joined_at=profile.joined_at,
        )

    def list_collaborators(self, chat_id: str) -> List[CollaboratorProfileDTO]:
        ledger, _ = self._get_bundle(chat_id)
        return [
            CollaboratorProfileDTO(
                collaborator_id=c.collaborator_id,
                collaborator_type=CollaboratorTypeEnum(c.collaborator_type.value),
                name=c.name,
                principal_human_id=c.principal_human_id,
                role_description=c.role_description,
                joined_at=c.joined_at,
            )
            for c in ledger.list_collaborators()
        ]

    def init_document(self, chat_id: str, req: InitDocumentRequest) -> List[DocumentBlockDTO]:
        ledger, _ = self._get_bundle(chat_id)
        ledger.document_id = req.document_id
        ledger.title = req.title
        blocks = [
            DocumentBlock(
                block_id=b.block_id,
                block_type=BlockType(b.block_type.value),
                content=b.content,
                version=b.version,
                last_author_id=b.last_author_id,
                last_updated_at=b.last_updated_at,
            )
            for b in req.blocks
        ]
        ledger.init_document(blocks)
        return [self._to_block_dto(b) for b in ledger.list_blocks()]

    def list_blocks(self, chat_id: str) -> List[DocumentBlockDTO]:
        ledger, _ = self._get_bundle(chat_id)
        return [self._to_block_dto(b) for b in ledger.list_blocks()]

    def render_markdown(self, chat_id: str) -> str:
        ledger, _ = self._get_bundle(chat_id)
        return ledger.render_markdown()

    def acquire_lease(self, chat_id: str, req: AcquireLeaseRequest) -> bool:
        ledger, _ = self._get_bundle(chat_id)
        return ledger.acquire_block_lease(
            block_id=req.block_id,
            author_id=req.author_id,
            duration_seconds=req.duration_seconds,
        )

    def release_lease(self, chat_id: str, req: ReleaseLeaseRequest) -> bool:
        ledger, _ = self._get_bundle(chat_id)
        return ledger.release_block_lease(
            block_id=req.block_id,
            author_id=req.author_id,
        )

    def apply_delta(self, chat_id: str, req: ApplyDeltaRequest) -> DocumentBlockDTO:
        ledger, _ = self._get_bundle(chat_id)
        block = ledger.apply_delta(
            block_id=req.block_id,
            operation=DeltaOperation(req.operation.value),
            author_id=req.author_id,
            new_content=req.new_content,
            intent_reason=req.intent_reason,
            block_type=BlockType(req.block_type.value),
        )
        return self._to_block_dto(block)

    def get_deltas(
        self, chat_id: str, block_id: Optional[str] = None, author_id: Optional[str] = None
    ) -> List[DeltaEntryDTO]:
        ledger, _ = self._get_bundle(chat_id)
        return [self._to_delta_dto(d) for d in ledger.get_deltas(block_id=block_id, author_id=author_id)]

    def get_contributions(self, chat_id: str) -> Dict[str, int]:
        ledger, _ = self._get_bundle(chat_id)
        return ledger.get_author_contributions()

    def arbitrate_conflict(
        self, chat_id: str, req: ArbitrateConflictRequest
    ) -> ArbitrationVerdictDTO:
        _, arbitrator = self._get_bundle(chat_id)
        verdict = arbitrator.detect_and_arbitrate(
            block_id=req.block_id,
            first_author_id=req.first_author_id,
            first_content=req.first_content,
            first_reason=req.first_reason,
            second_author_id=req.second_author_id,
            second_content=req.second_content,
            second_reason=req.second_reason,
            strategy=ArbitrationStrategy(req.strategy.value),
        )
        return ArbitrationVerdictDTO(
            resolved=verdict.resolved,
            winning_content=verdict.winning_content,
            strategy=ArbitrationStrategyEnum(verdict.strategy.value),
            summary=verdict.summary,
            staging_proposals=[self._to_proposal_dto(p) for p in verdict.staging_proposals],
            timestamp=verdict.timestamp,
        )

    def list_proposals(
        self, chat_id: str, block_id: Optional[str] = None
    ) -> List[StagingProposalDTO]:
        _, arbitrator = self._get_bundle(chat_id)
        return [self._to_proposal_dto(p) for p in arbitrator.list_proposals(block_id=block_id)]

    def accept_proposal(
        self, chat_id: str, proposal_id: str, reviewer_id: str
    ) -> Optional[StagingProposalDTO]:
        _, arbitrator = self._get_bundle(chat_id)
        prop = arbitrator.accept_proposal(proposal_id=proposal_id, reviewer_id=reviewer_id)
        return self._to_proposal_dto(prop) if prop else None

    def list_conflicts(self, chat_id: str) -> List[ConflictRecordDTO]:
        _, arbitrator = self._get_bundle(chat_id)
        return [self._to_conflict_dto(c) for c in arbitrator.list_conflicts()]

    def reset_session(self, chat_id: str) -> None:
        self._ledgers.pop(chat_id, None)
        self._arbitrators.pop(chat_id, None)


_singleton_coauthoring_ledger_service = CoAuthoringLedgerService()


def get_coauthoring_ledger_service() -> CoAuthoringLedgerService:
    """Return the global singleton instance of CoAuthoringLedgerService."""
    return _singleton_coauthoring_ledger_service
