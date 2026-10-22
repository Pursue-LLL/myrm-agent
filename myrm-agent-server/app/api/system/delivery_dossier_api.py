"""
[INPUT]: Delivery evidence payloads, verification receipts, acceptance verdicts, and friction trial reports.
[OUTPUT]: Immutable DeliveryEvidenceDossier records, SHA256 integrity checksums, and stratified AssetFrictionMetric evaluations.
[POS]: myrm-agent/myrm-agent-server/app/api/system/delivery_dossier_api.py
"""

from typing import List, Optional

from fastapi import APIRouter, HTTPException, Path, Query, status
from pydantic import BaseModel, Field

from myrm_agent_harness.observability.delivery_dossier import (
    AgentPersonaFingerprint,
    AssetFrictionCalculator,
    AssetFrictionMetric,
    AssetHealthTag,
    DeliveryDossierRecorder,
    DeliveryEvidenceDossier,
    ExecutionMode,
    PhysicalVerificationReceipt,
    TaskSpecRecord,
    ToolExecutionTraceItem,
    UserAcceptanceStatus,
)

router = APIRouter(tags=["delivery-dossier"])

_recorder = DeliveryDossierRecorder()
_friction_calc = AssetFrictionCalculator(min_samples_threshold=3)


# --- Pydantic Schemas ---

class TaskSpecSchema(BaseModel):
    task_goal: str
    acceptance_criteria: List[str] = Field(default_factory=list)
    non_goals: List[str] = Field(default_factory=list)


class AgentPersonaSchema(BaseModel):
    agent_id: str
    model_name: str
    prompt_hash: str
    mounted_skills: List[str] = Field(default_factory=list)


class ToolTraceSchema(BaseModel):
    tool_name: str
    arguments_summary: str
    duration_ms: float
    exit_code: int
    error_message: Optional[str] = None


class VerificationReceiptSchema(BaseModel):
    test_suite_exit_code: int
    passed_tests_count: int
    failed_tests_count: int
    artifact_path: str
    artifact_sha256: str
    verified_at: str


class ArchiveDossierRequest(BaseModel):
    task_id: str
    execution_mode: str = "MULTI_TURN_AGENT"
    spec: TaskSpecSchema
    persona: AgentPersonaSchema
    tool_traces: List[ToolTraceSchema] = Field(default_factory=list)
    verification: VerificationReceiptSchema
    acceptance: str = "ACCEPTED"
    total_tokens_consumed: int = Field(default=0, ge=0)
    wasted_friction_tokens: int = Field(default=0, ge=0)
    rework_count: int = Field(default=0, ge=0)


class DeliveryEvidenceDossierResponse(BaseModel):
    dossier_id: str
    task_id: str
    execution_mode: str
    spec: TaskSpecSchema
    persona: AgentPersonaSchema
    tool_traces: List[ToolTraceSchema]
    verification: VerificationReceiptSchema
    acceptance: str
    total_tokens_consumed: int
    wasted_friction_tokens: int
    rework_count: int
    dossier_checksum_sha256: str
    created_at: str


class RecordFrictionTrialRequest(BaseModel):
    skill_id: str
    model_name: str
    execution_mode: str = "MULTI_TURN_AGENT"
    accepted: bool
    retries: int = Field(default=0, ge=0)
    rework: bool = False
    wasted_tokens: int = Field(default=0, ge=0)
    baseline_tokens: int = Field(default=1000, ge=1)


class AssetFrictionMetricResponse(BaseModel):
    skill_id: str
    model_name: str
    execution_mode: str
    sample_count: int
    true_efficacy_rate_pct: float
    friction_index: float
    total_wasted_tokens: int
    rework_count: int
    retry_count: int
    health_tag: str
    governance_advice: str


def _convert_dossier_to_response(d: DeliveryEvidenceDossier) -> DeliveryEvidenceDossierResponse:
    return DeliveryEvidenceDossierResponse(
        dossier_id=d.dossier_id,
        task_id=d.task_id,
        execution_mode=d.execution_mode.value,
        spec=TaskSpecSchema(
            task_goal=d.spec.task_goal,
            acceptance_criteria=d.spec.acceptance_criteria,
            non_goals=d.spec.non_goals,
        ),
        persona=AgentPersonaSchema(
            agent_id=d.persona.agent_id,
            model_name=d.persona.model_name,
            prompt_hash=d.persona.prompt_hash,
            mounted_skills=d.persona.mounted_skills,
        ),
        tool_traces=[
            ToolTraceSchema(
                tool_name=t.tool_name,
                arguments_summary=t.arguments_summary,
                duration_ms=t.duration_ms,
                exit_code=t.exit_code,
                error_message=t.error_message,
            )
            for t in d.tool_traces
        ],
        verification=VerificationReceiptSchema(
            test_suite_exit_code=d.verification.test_suite_exit_code,
            passed_tests_count=d.verification.passed_tests_count,
            failed_tests_count=d.verification.failed_tests_count,
            artifact_path=d.verification.artifact_path,
            artifact_sha256=d.verification.artifact_sha256,
            verified_at=d.verification.verified_at,
        ),
        acceptance=d.acceptance.value,
        total_tokens_consumed=d.total_tokens_consumed,
        wasted_friction_tokens=d.wasted_friction_tokens,
        rework_count=d.rework_count,
        dossier_checksum_sha256=d.dossier_checksum_sha256,
        created_at=d.created_at,
    )


def _convert_metric_to_response(m: AssetFrictionMetric) -> AssetFrictionMetricResponse:
    return AssetFrictionMetricResponse(
        skill_id=m.skill_id,
        model_name=m.model_name,
        execution_mode=m.execution_mode.value,
        sample_count=m.sample_count,
        true_efficacy_rate_pct=m.true_efficacy_rate_pct,
        friction_index=m.friction_index,
        total_wasted_tokens=m.total_wasted_tokens,
        rework_count=m.rework_count,
        retry_count=m.retry_count,
        health_tag=m.health_tag.value,
        governance_advice=m.governance_advice,
    )


# --- Route Handlers ---

@router.post(
    "/delivery-dossier/archive",
    response_model=DeliveryEvidenceDossierResponse,
    status_code=status.HTTP_200_OK,
)
async def archive_delivery_dossier(req: ArchiveDossierRequest) -> DeliveryEvidenceDossierResponse:
    """Archives an immutable cross-agent delivery evidence dossier with physical test receipts."""
    try:
        exec_mode = ExecutionMode(req.execution_mode)
    except ValueError:
        exec_mode = ExecutionMode.MULTI_TURN_AGENT

    try:
        acceptance_status = UserAcceptanceStatus(req.acceptance)
    except ValueError:
        acceptance_status = UserAcceptanceStatus.ACCEPTED

    dossier = _recorder.create_dossier(
        task_id=req.task_id,
        execution_mode=exec_mode,
        spec=TaskSpecRecord(
            task_goal=req.spec.task_goal,
            acceptance_criteria=req.spec.acceptance_criteria,
            non_goals=req.spec.non_goals,
        ),
        persona=AgentPersonaFingerprint(
            agent_id=req.persona.agent_id,
            model_name=req.persona.model_name,
            prompt_hash=req.persona.prompt_hash,
            mounted_skills=req.persona.mounted_skills,
        ),
        tool_traces=[
            ToolExecutionTraceItem(
                tool_name=t.tool_name,
                arguments_summary=t.arguments_summary,
                duration_ms=t.duration_ms,
                exit_code=t.exit_code,
                error_message=t.error_message,
            )
            for t in req.tool_traces
        ],
        verification=PhysicalVerificationReceipt(
            test_suite_exit_code=req.verification.test_suite_exit_code,
            passed_tests_count=req.verification.passed_tests_count,
            failed_tests_count=req.verification.failed_tests_count,
            artifact_path=req.verification.artifact_path,
            artifact_sha256=req.verification.artifact_sha256,
            verified_at=req.verification.verified_at,
        ),
        acceptance=acceptance_status,
        total_tokens_consumed=req.total_tokens_consumed,
        wasted_friction_tokens=req.wasted_friction_tokens,
        rework_count=req.rework_count,
    )
    return _convert_dossier_to_response(dossier)


@router.get(
    "/delivery-dossier/{dossier_id}",
    response_model=DeliveryEvidenceDossierResponse,
    status_code=status.HTTP_200_OK,
)
async def get_delivery_dossier(
    dossier_id: str = Path(..., description="Unique delivery dossier ID"),
) -> DeliveryEvidenceDossierResponse:
    """Retrieves an immutable delivery evidence dossier by ID."""
    dossier = _recorder.get_dossier(dossier_id)
    if not dossier:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dossier {dossier_id} not found",
        )
    return _convert_dossier_to_response(dossier)


@router.get(
    "/delivery-dossier/by-task/{task_id}",
    response_model=DeliveryEvidenceDossierResponse,
    status_code=status.HTTP_200_OK,
)
async def get_dossier_by_task(
    task_id: str = Path(..., description="Task ID associated with the dossier"),
) -> DeliveryEvidenceDossierResponse:
    """Retrieves a delivery dossier associated with a specific task."""
    dossier = _recorder.get_dossier_by_task(task_id)
    if not dossier:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No dossier found for task {task_id}",
        )
    return _convert_dossier_to_response(dossier)


@router.post(
    "/delivery-dossier/record-friction-trial",
    status_code=status.HTTP_200_OK,
)
async def record_friction_trial(req: RecordFrictionTrialRequest) -> dict[str, str]:
    """Records a trial execution outcome for stratified asset friction evaluation."""
    try:
        exec_mode = ExecutionMode(req.execution_mode)
    except ValueError:
        exec_mode = ExecutionMode.MULTI_TURN_AGENT

    _friction_calc.record_trial(
        skill_id=req.skill_id,
        model_name=req.model_name,
        execution_mode=exec_mode,
        accepted=req.accepted,
        retries=req.retries,
        rework=req.rework,
        wasted_tokens=req.wasted_tokens,
        baseline_tokens=req.baseline_tokens,
    )
    return {"status": "ok", "message": f"Recorded trial for {req.skill_id}"}


@router.get(
    "/delivery-dossier/asset-friction/all",
    response_model=List[AssetFrictionMetricResponse],
    status_code=status.HTTP_200_OK,
)
async def list_all_asset_friction() -> List[AssetFrictionMetricResponse]:
    """Lists stratified efficacy and friction metrics across all monitored skills and tools."""
    metrics = _friction_calc.list_all_assets()
    return [_convert_metric_to_response(m) for m in metrics]


@router.get(
    "/delivery-dossier/asset-friction/{skill_id}",
    response_model=AssetFrictionMetricResponse,
    status_code=status.HTTP_200_OK,
)
async def get_asset_friction(
    skill_id: str = Path(..., description="Target skill ID"),
    model_name: str = Query("claude-3-5-sonnet", description="Model name stratification"),
    execution_mode: str = Query("MULTI_TURN_AGENT", description="Execution mode"),
) -> AssetFrictionMetricResponse:
    """Evaluates stratified friction metrics for a specific skill and model combination."""
    try:
        exec_mode = ExecutionMode(execution_mode)
    except ValueError:
        exec_mode = ExecutionMode.MULTI_TURN_AGENT

    metric = _friction_calc.evaluate_asset(
        skill_id=skill_id,
        model_name=model_name,
        execution_mode=exec_mode,
    )
    return _convert_metric_to_response(metric)
