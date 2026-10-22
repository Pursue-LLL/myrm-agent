"""[INPUT] CreateTriRoleSessionRequest, PlanSubmissionRequest, GenerationSubmissionRequest, EvaluateStageRequest, RestoreFromManifestRequest.
[OUTPUT] TriRoleService orchestrating Planner-Generator-Evaluator cognitive separation and artifact handoff.
[POS] Service layer for Tri-Role Separation and Artifact Handoff Pipeline (Item 40).
"""

from __future__ import annotations

import logging
import threading

from myrm_agent_harness.agent.coordination.tri_role import (
    AcceptanceCriterion,
    ArtifactManifest,
    EvaluationVerdict,
    TriRolePipelineCoordinator,
    TriRolePipelineStage,
    TriRoleSessionState,
)

from app.schemas.tri_role import (
    AcceptanceCriterionDTO,
    ArtifactManifestDTO,
    CreateTriRoleSessionRequest,
    EvaluateStageRequest,
    EvaluationVerdictDTO,
    GenerationSubmissionRequest,
    PlanSubmissionRequest,
    RestoreFromManifestRequest,
    StageStatusEnum,
    TriRolePipelineStageDTO,
    TriRoleSessionResponse,
)

logger = logging.getLogger(__name__)


def _criterion_to_dto(c: AcceptanceCriterion) -> AcceptanceCriterionDTO:
    return AcceptanceCriterionDTO(
        criterion_id=c.criterion_id,
        description=c.description,
        assertion_rule=c.assertion_rule,
        is_satisfied=c.is_satisfied,
    )


def _criterion_from_dto(dto: AcceptanceCriterionDTO) -> AcceptanceCriterion:
    return AcceptanceCriterion(
        criterion_id=dto.criterion_id,
        description=dto.description,
        assertion_rule=dto.assertion_rule,
        is_satisfied=dto.is_satisfied,
    )


def _verdict_to_dto(v: EvaluationVerdict | None) -> EvaluationVerdictDTO | None:
    if v is None:
        return None
    return EvaluationVerdictDTO(
        is_accepted=v.is_accepted,
        score=v.score,
        evaluator_notes=v.evaluator_notes,
        criteria_results=dict(v.criteria_results),
        evaluated_at=v.evaluated_at,
    )


def _manifest_to_dto(m: ArtifactManifest | None) -> ArtifactManifestDTO | None:
    if m is None:
        return None
    return ArtifactManifestDTO(
        manifest_id=m.manifest_id,
        session_id=m.session_id,
        stage_index=m.stage_index,
        produced_files=list(m.produced_files),
        passed_assertions=list(m.passed_assertions),
        key_constraints=list(m.key_constraints),
        pending_todos=list(m.pending_todos),
        created_at=m.created_at,
    )


def _manifest_from_dto(dto: ArtifactManifestDTO) -> ArtifactManifest:
    return ArtifactManifest(
        manifest_id=dto.manifest_id,
        session_id=dto.session_id,
        stage_index=dto.stage_index,
        produced_files=list(dto.produced_files),
        passed_assertions=list(dto.passed_assertions),
        key_constraints=list(dto.key_constraints),
        pending_todos=list(dto.pending_todos),
        created_at=dto.created_at,
    )


def _stage_to_dto(stage: TriRolePipelineStage) -> TriRolePipelineStageDTO:
    return TriRolePipelineStageDTO(
        stage_id=stage.stage_id,
        stage_name=stage.stage_name,
        status=StageStatusEnum(stage.status.value),
        planner_output=stage.planner_output,
        criteria=[_criterion_to_dto(c) for c in stage.criteria],
        generator_output=stage.generator_output,
        produced_files=list(stage.produced_files),
        evaluation=_verdict_to_dto(stage.evaluation),
        manifest=_manifest_to_dto(stage.manifest),
    )


def _session_to_response(session: TriRoleSessionState) -> TriRoleSessionResponse:
    return TriRoleSessionResponse(
        session_id=session.session_id,
        task_description=session.task_description,
        stages=[_stage_to_dto(s) for s in session.stages],
        current_stage_index=session.current_stage_index,
        is_completed=session.is_completed,
        created_at=session.created_at,
        updated_at=session.updated_at,
    )


class TriRoleService:
    """Service mediating tri-role separation, cognitive isolation, and artifact handoffs."""

    def __init__(self) -> None:
        self._coordinator = TriRolePipelineCoordinator()
        self._lock = threading.Lock()

    def create_session(self, req: CreateTriRoleSessionRequest) -> TriRoleSessionResponse:
        with self._lock:
            state = self._coordinator.create_session(
                session_id=req.session_id,
                task_description=req.task_description,
                stage_names=req.stage_names,
            )
            logger.info("Created tri-role session '%s' with %d stages", req.session_id, len(req.stage_names))
            return _session_to_response(state)

    def get_session(self, session_id: str) -> TriRoleSessionResponse | None:
        with self._lock:
            state = self._coordinator.get_session(session_id)
            if state is None:
                return None
            return _session_to_response(state)

    def submit_plan(
        self, session_id: str, stage_id: str, req: PlanSubmissionRequest
    ) -> TriRolePipelineStageDTO:
        with self._lock:
            domain_criteria = [_criterion_from_dto(c) for c in req.criteria]
            updated_stage = self._coordinator.submit_plan(
                session_id=session_id,
                stage_id=stage_id,
                planner_output=req.planner_output,
                criteria=domain_criteria,
            )
            logger.info("Submitted plan for stage '%s' in session '%s'", stage_id, session_id)
            return _stage_to_dto(updated_stage)

    def submit_generation(
        self, session_id: str, stage_id: str, req: GenerationSubmissionRequest
    ) -> TriRolePipelineStageDTO:
        with self._lock:
            updated_stage = self._coordinator.submit_generation(
                session_id=session_id,
                stage_id=stage_id,
                generator_output=req.generator_output,
                produced_files=req.produced_files,
            )
            logger.info("Submitted generation for stage '%s' in session '%s'", stage_id, session_id)
            return _stage_to_dto(updated_stage)

    def evaluate_stage(
        self, session_id: str, stage_id: str, req: EvaluateStageRequest
    ) -> EvaluationVerdictDTO:
        with self._lock:
            verdict = self._coordinator.evaluate_stage(
                session_id=session_id,
                stage_id=stage_id,
                evaluator_notes=req.evaluator_notes,
                criteria_evaluations=req.criteria_evaluations,
                min_pass_rate=req.min_pass_rate,
            )
            logger.info(
                "Evaluated stage '%s' in session '%s' (accepted=%s, score=%.2f)",
                stage_id,
                session_id,
                verdict.is_accepted,
                verdict.score,
            )
            verdict_dto = _verdict_to_dto(verdict)
            if verdict_dto is None:
                msg = "Evaluation verdict serialization failed"
                raise RuntimeError(msg)
            return verdict_dto

    def advance_to_next_stage(self, session_id: str) -> TriRoleSessionResponse:
        with self._lock:
            updated_session = self._coordinator.advance_to_next_stage(session_id)
            logger.info(
                "Advanced session '%s' to stage index %d (completed=%s)",
                session_id,
                updated_session.current_stage_index,
                updated_session.is_completed,
            )
            return _session_to_response(updated_session)

    def export_manifest(
        self, session_id: str, stage_id: str | None = None
    ) -> ArtifactManifestDTO:
        with self._lock:
            manifest = self._coordinator.export_handoff_manifest(session_id, stage_id)
            logger.info("Exported manifest '%s' from session '%s'", manifest.manifest_id, session_id)
            dto = _manifest_to_dto(manifest)
            if dto is None:
                msg = "Manifest serialization failed"
                raise RuntimeError(msg)
            return dto

    def restore_from_manifest(
        self, req: RestoreFromManifestRequest
    ) -> TriRoleSessionResponse:
        with self._lock:
            domain_manifest = _manifest_from_dto(req.manifest)
            restored_state = self._coordinator.restore_session_from_manifest(
                manifest=domain_manifest,
                new_session_id=req.new_session_id,
                task_description=req.task_description,
                subsequent_stage_names=req.subsequent_stage_names,
            )
            logger.info(
                "Restored new session '%s' from manifest '%s'",
                req.new_session_id,
                req.manifest.manifest_id,
            )
            return _session_to_response(restored_state)


_global_tri_role_service = TriRoleService()


def get_tri_role_service() -> TriRoleService:
    """Retrieve global singleton TriRoleService instance."""
    return _global_tri_role_service
