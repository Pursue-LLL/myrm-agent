"""Service layer for Council of Agents Multi-Model Deliberation Protocol (Item 65).

[INPUT]
- CreateCouncilSessionRequest, SubmitProposalRequest, SubmitCritiqueRequest,
  SubmitRebuttalRequest, AdvancePhaseRequest schemas.
- CouncilDeliberationPipeline from harness.

[OUTPUT]
- CouncilSessionDTO, CouncilProposalDTO, CritiqueItemDTO, ConsensusVerdictDTO.

[POS]
- Bridge between FastAPI council router and underlying harness CouncilDeliberationPipeline.
"""

from __future__ import annotations

import threading
from typing import ClassVar

from myrm_agent_harness.agent.sub_agents.council import (
    ConsensusVerdict,
    CouncilDeliberationPipeline,
    CouncilProposal,
    CouncilSession,
    CritiqueItem,
    CritiqueSeverity,
    DeliberationPhase,
)

from app.schemas.council import (
    AdvancePhaseRequest,
    ConsensusVerdictDTO,
    CouncilProposalDTO,
    CouncilSessionDTO,
    CreateCouncilSessionRequest,
    CritiqueItemDTO,
    CritiqueSeverityDTOEnum,
    DeliberationPhaseDTOEnum,
    SubmitCritiqueRequest,
    SubmitProposalRequest,
    SubmitRebuttalRequest,
)


class CouncilDeliberationService:
    """Thread-safe orchestration service managing multi-model council deliberation sessions."""

    _pipeline: ClassVar[CouncilDeliberationPipeline] = CouncilDeliberationPipeline()
    _lock: ClassVar[threading.Lock] = threading.Lock()

    @classmethod
    def _to_proposal_dto(cls, p: CouncilProposal) -> CouncilProposalDTO:
        return CouncilProposalDTO(
            proposal_id=p.proposal_id,
            member_id=p.member_id,
            model_name=p.model_name,
            title=p.title,
            reasoning_steps=list(p.reasoning_steps),
            key_arguments=list(p.key_arguments),
            confidence_score=p.confidence_score,
        )

    @classmethod
    def _to_critique_dto(cls, c: CritiqueItem) -> CritiqueItemDTO:
        return CritiqueItemDTO(
            critique_id=c.critique_id,
            source_member_id=c.source_member_id,
            target_member_id=c.target_member_id,
            target_proposal_id=c.target_proposal_id,
            critique_points=list(c.critique_points),
            severity=CritiqueSeverityDTOEnum(c.severity.value),
            defense_rebuttal=c.defense_rebuttal,
        )

    @classmethod
    def _to_consensus_dto(cls, v: ConsensusVerdict) -> ConsensusVerdictDTO:
        return ConsensusVerdictDTO(
            verdict_id=v.verdict_id,
            final_decision=v.final_decision,
            confidence_rating=v.confidence_rating,
            key_tradeoffs=list(v.key_tradeoffs),
            participating_models=list(v.participating_models),
            dissenting_opinions=list(v.dissenting_opinions),
        )

    @classmethod
    def _to_session_dto(cls, s: CouncilSession) -> CouncilSessionDTO:
        proposals_map = {
            pid: cls._to_proposal_dto(p) for pid, p in s.proposals.items()
        }
        critiques_list = [cls._to_critique_dto(c) for c in s.critiques]
        consensus_dto = cls._to_consensus_dto(s.consensus) if s.consensus else None
        return CouncilSessionDTO(
            session_id=s.session_id,
            deliberation_topic=s.deliberation_topic,
            phase=DeliberationPhaseDTOEnum(s.phase.value),
            proposals=proposals_map,
            critiques=critiques_list,
            consensus=consensus_dto,
            created_at=s.created_at,
            updated_at=s.updated_at,
        )

    @classmethod
    def create_session(cls, req: CreateCouncilSessionRequest) -> CouncilSessionDTO:
        """Create a new multi-model deliberation session."""
        with cls._lock:
            session = cls._pipeline.create_session(
                session_id=req.session_id,
                topic=req.deliberation_topic,
            )
            return cls._to_session_dto(session)

    @classmethod
    def get_session(cls, session_id: str) -> CouncilSessionDTO | None:
        """Fetch session state by ID."""
        with cls._lock:
            session = cls._pipeline.get_session(session_id)
            if session is None:
                return None
            return cls._to_session_dto(session)

    @classmethod
    def list_sessions(cls) -> list[CouncilSessionDTO]:
        """List all active council sessions."""
        with cls._lock:
            sessions = cls._pipeline.list_sessions()
            return [cls._to_session_dto(s) for s in sessions]

    @classmethod
    def submit_proposal(cls, session_id: str, req: SubmitProposalRequest) -> CouncilSessionDTO:
        """Submit a model proposal to a session."""
        with cls._lock:
            p = req.proposal
            proposal = CouncilProposal(
                proposal_id=p.proposal_id,
                member_id=p.member_id,
                model_name=p.model_name,
                title=p.title,
                reasoning_steps=list(p.reasoning_steps),
                key_arguments=list(p.key_arguments),
                confidence_score=p.confidence_score,
            )
            session = cls._pipeline.submit_proposal(session_id, proposal)
            return cls._to_session_dto(session)

    @classmethod
    def submit_critique(cls, session_id: str, req: SubmitCritiqueRequest) -> CouncilSessionDTO:
        """Submit an anonymous cross-model critique point."""
        with cls._lock:
            c = req.critique
            critique = CritiqueItem(
                critique_id=c.critique_id,
                source_member_id=c.source_member_id,
                target_member_id=c.target_member_id,
                target_proposal_id=c.target_proposal_id,
                critique_points=list(c.critique_points),
                severity=CritiqueSeverity(c.severity.value),
                defense_rebuttal=c.defense_rebuttal,
            )
            session = cls._pipeline.submit_critique(session_id, critique)
            return cls._to_session_dto(session)

    @classmethod
    def submit_rebuttal(
        cls,
        session_id: str,
        critique_id: str,
        req: SubmitRebuttalRequest,
    ) -> CouncilSessionDTO:
        """Add a defense rebuttal to an existing critique."""
        with cls._lock:
            session = cls._pipeline.submit_rebuttal(
                session_id=session_id,
                critique_id=critique_id,
                rebuttal_text=req.rebuttal_text,
            )
            return cls._to_session_dto(session)

    @classmethod
    def advance_phase(cls, session_id: str, req: AdvancePhaseRequest) -> CouncilSessionDTO:
        """Advance session to the next deliberation phase or specified target phase."""
        with cls._lock:
            target_phase = (
                DeliberationPhase(req.target_phase.value) if req.target_phase else None
            )
            session = cls._pipeline.advance_phase(session_id, target_phase)
            return cls._to_session_dto(session)

    @classmethod
    def clear(cls) -> None:
        """Reset service state for isolated test runs."""
        with cls._lock:
            cls._pipeline.clear()
