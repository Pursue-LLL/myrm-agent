from fastapi import APIRouter, HTTPException, Path

from app.schemas.orthogonal_reviewer import (
    ArbitrateRequest,
    ArbitrationVerdictDTO,
    AutoFixRequest,
    AutoFixResponse,
    BlindReviewRequest,
    FullReviewRequest,
    FullReviewResponse,
    IntentReviewRequest,
    ReviewerReportDTO,
)
from app.services.agent.orthogonal_reviewer_service import OrthogonalReviewerService

router = APIRouter(prefix="/agents/orthogonal-reviewer", tags=["Orthogonal Reviewer & Arbiter"])


@router.post("/review-intent", response_model=ReviewerReportDTO)
async def review_intent_alignment(request: IntentReviewRequest) -> ReviewerReportDTO:
    """Execute Reviewer A: Shared-context intent alignment and architectural drift review."""
    service = OrthogonalReviewerService.get_instance()
    return service.review_intent(
        task_prompt=request.task_prompt,
        architecture_plan=request.architecture_plan,
        code_diff=request.code_diff,
        files_touched=request.files_touched,
    )


@router.post("/review-blind", response_model=ReviewerReportDTO)
async def review_blind_clean_context(request: BlindReviewRequest) -> ReviewerReportDTO:
    """Execute Reviewer B: Zero-bias clean-context review on diff and public signatures."""
    service = OrthogonalReviewerService.get_instance()
    return service.review_blind(
        code_diff=request.code_diff,
        files_touched=request.files_touched,
        public_signatures=request.public_signatures,
    )


@router.post("/arbitrate", response_model=ArbitrationVerdictDTO)
async def arbitrate_dual_reports(request: ArbitrateRequest) -> ArbitrationVerdictDTO:
    """Synthesize Reviewer A and Reviewer B reports into a deduplicated arbitration verdict."""
    service = OrthogonalReviewerService.get_instance()
    return service.arbitrate(
        session_id=request.session_id,
        report_a_dto=request.report_a,
        report_b_dto=request.report_b,
    )


@router.post("/full-review", response_model=FullReviewResponse)
async def conduct_full_orthogonal_review(request: FullReviewRequest) -> FullReviewResponse:
    """Conduct full pipeline: execute both Reviewer A and B in parallel, then synthesize verdict."""
    service = OrthogonalReviewerService.get_instance()
    return service.conduct_full_review(
        session_id=request.session_id,
        task_prompt=request.task_prompt,
        architecture_plan=request.architecture_plan,
        code_diff=request.code_diff,
        files_touched=request.files_touched,
        public_signatures=request.public_signatures,
    )


@router.get("/sessions/{session_id}/verdict", response_model=ArbitrationVerdictDTO)
async def get_session_verdict(
    session_id: str = Path(..., description="Session identifier"),
) -> ArbitrationVerdictDTO:
    """Retrieve existing arbitration verdict for the given session."""
    service = OrthogonalReviewerService.get_instance()
    verdict = service.get_verdict(session_id)
    if not verdict:
        raise HTTPException(status_code=404, detail="Session review verdict not found")
    return verdict


@router.post("/sessions/{session_id}/auto-fix", response_model=AutoFixResponse)
async def apply_auto_fix_patch(
    session_id: str = Path(..., description="Session identifier"),
    request: AutoFixRequest = ...,  # type: ignore[assignment]
) -> AutoFixResponse:
    """Apply auto-fix patches for selected findings, transitioning gate status."""
    service = OrthogonalReviewerService.get_instance()
    return service.apply_auto_fix(session_id=session_id, finding_ids=request.finding_ids)
