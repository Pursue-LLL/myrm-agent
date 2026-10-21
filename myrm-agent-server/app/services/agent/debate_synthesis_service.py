"""[INPUT] schemas/debate_synthesis.py, myrm_agent_harness.agent.sub_agents.debate.synthesis_pattern.
[OUTPUT] DebateSynthesisService: Service layer managing hierarchical debate synthesis workflows and trade-off matrices.
[POS] Service coordinator bridging FastAPI HTTP endpoints with Harness HierarchicalDebateSynthesisEngine.
"""

from __future__ import annotations

import uuid

from myrm_agent_harness.agent.sub_agents.debate.synthesis_pattern import (
    CandidateProposal,
    HierarchicalDebateSynthesisEngine,
    SynthesisParticipant,
    SynthesisSubtask,
    SynthesisWorkflowState,
    TradeoffMatrix,
)

from app.schemas.debate_synthesis import (
    CandidateProposalDTO,
    CreateSynthesisWorkflowRequest,
    SubmitProposalRequest,
    SynthesisParticipantDTO,
    SynthesisSubtaskDTO,
    SynthesisWorkflowResponse,
    SynthesizeMatrixRequest,
    TradeoffMatrixDTO,
)


class DebateSynthesisService:
    """Service orchestrating hierarchical 3-stage leader-worker debate & synthesis workflows."""

    _instance: DebateSynthesisService | None = None

    def __init__(self, engine: HierarchicalDebateSynthesisEngine | None = None) -> None:
        self._engine = engine or HierarchicalDebateSynthesisEngine()

    @classmethod
    def get_instance(cls) -> DebateSynthesisService:
        """Singleton accessor."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @staticmethod
    def _participant_to_dto(p: SynthesisParticipant) -> SynthesisParticipantDTO:
        return SynthesisParticipantDTO(
            agent_id=p.agent_id,
            name=p.name,
            role=p.role,
            model=p.model,
        )

    @staticmethod
    def _subtask_to_dto(st: SynthesisSubtask) -> SynthesisSubtaskDTO:
        return SynthesisSubtaskDTO(
            task_id=st.task_id,
            title=st.title,
            assigned_role=st.assigned_role,
            assigned_agent_id=st.assigned_agent_id,
            description=st.description,
            depends_on=list(st.depends_on),
            status=st.status,
            output_summary=st.output_summary,
        )

    @staticmethod
    def _proposal_to_dto(pr: CandidateProposal) -> CandidateProposalDTO:
        return CandidateProposalDTO(
            proposal_id=pr.proposal_id,
            title=pr.title,
            author_role=pr.author_role,
            author_agent_id=pr.author_agent_id,
            summary=pr.summary,
            pros=list(pr.pros),
            cons=list(pr.cons),
            dimension_scores=dict(pr.dimension_scores),
            is_recommended=pr.is_recommended,
        )

    @classmethod
    def _matrix_to_dto(cls, tm: TradeoffMatrix) -> TradeoffMatrixDTO:
        return TradeoffMatrixDTO(
            matrix_id=tm.matrix_id,
            workflow_id=tm.workflow_id,
            dimensions=list(tm.dimensions),
            dimension_weights=dict(tm.dimension_weights),
            proposals=[cls._proposal_to_dto(p) for p in tm.proposals],
            winner_proposal_id=tm.winner_proposal_id,
            recommendation_rationale=tm.recommendation_rationale,
            created_at=tm.created_at,
        )

    @classmethod
    def _state_to_response(cls, state: SynthesisWorkflowState) -> SynthesisWorkflowResponse:
        return SynthesisWorkflowResponse(
            workflow_id=state.workflow_id,
            chat_id=state.chat_id,
            topic=state.topic,
            phase=state.phase,
            participants=[cls._participant_to_dto(p) for p in state.participants],
            subtasks=[cls._subtask_to_dto(st) for st in state.subtasks],
            proposals=[cls._proposal_to_dto(pr) for pr in state.proposals],
            matrix=cls._matrix_to_dto(state.matrix) if state.matrix else None,
            round_index=state.round_index,
            max_rounds=state.max_rounds,
            created_at=state.created_at,
            updated_at=state.updated_at,
        )

    def create_workflow(
        self,
        chat_id: str,
        req: CreateSynthesisWorkflowRequest,
    ) -> SynthesisWorkflowResponse:
        """Create and initialize a new 3-stage consulting workflow."""
        workflow_id = req.workflow_id or f"syn-wf-{uuid.uuid4().hex[:10]}"
        state = self._engine.create_workflow(
            workflow_id=workflow_id,
            chat_id=chat_id,
            topic=req.topic,
            leader_id=req.leader_id,
            researcher_id=req.researcher_id,
            auditor_id=req.auditor_id,
            max_rounds=req.max_rounds,
        )
        return self._state_to_response(state)

    def get_workflow(self, workflow_id: str) -> SynthesisWorkflowResponse | None:
        """Fetch workflow by ID."""
        state = self._engine.get_workflow(workflow_id)
        if not state:
            return None
        return self._state_to_response(state)

    def list_workflows(self, chat_id: str) -> list[SynthesisWorkflowResponse]:
        """List workflows for a chat session."""
        workflows = self._engine.list_workflows(chat_id)
        return [self._state_to_response(w) for w in workflows]

    def auto_decompose(
        self,
        workflow_id: str,
        leader_agent_id: str,
    ) -> SynthesisWorkflowResponse:
        """Leader derives subtask DAG with explicit dependencies."""
        state = self._engine.auto_decompose(
            workflow_id=workflow_id,
            leader_agent_id=leader_agent_id,
        )
        return self._state_to_response(state)

    def submit_proposal(
        self,
        workflow_id: str,
        req: SubmitProposalRequest,
    ) -> SynthesisWorkflowResponse:
        """Submit a specialist proposal."""
        proposal_id = req.proposal_id or f"prop-{uuid.uuid4().hex[:8]}"
        proposal = CandidateProposal(
            proposal_id=proposal_id,
            title=req.title,
            author_role=req.author_role,
            author_agent_id=req.author_agent_id,
            summary=req.summary,
            pros=list(req.pros),
            cons=list(req.cons),
            dimension_scores=dict(req.dimension_scores),
        )
        state = self._engine.submit_proposal(workflow_id=workflow_id, proposal=proposal)
        return self._state_to_response(state)

    def advance_cross_debate(self, workflow_id: str) -> SynthesisWorkflowResponse:
        """Advance cross debate round."""
        state = self._engine.advance_cross_debate(workflow_id=workflow_id)
        return self._state_to_response(state)

    def synthesize_decision_matrix(
        self,
        workflow_id: str,
        req: SynthesizeMatrixRequest,
    ) -> TradeoffMatrixDTO:
        """Compile multidimensional decision trade-off matrix."""
        matrix = self._engine.synthesize_decision_matrix(
            workflow_id=workflow_id,
            custom_weights=req.custom_weights,
            custom_rationale=req.custom_rationale,
        )
        return self._matrix_to_dto(matrix)
