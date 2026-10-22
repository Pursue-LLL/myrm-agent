"""FastAPI router for Open Source Handoff Gap Lint & Pipeline Integrity Doctor (Item 53).

[INPUT]
- app.schemas.pipeline_integrity::{
    LintPipelineRequest,
    AutoHealPipelineRequest,
    InspectDecisionChainRequest,
  }
- app.services.agent.pipeline_integrity_service::{
    PipelineIntegrityService,
  }

[OUTPUT]
- REST endpoints under /agents/pipeline-integrity for pipeline integrity linting,
  gap diagnostics, auto-healing, and transparent decision chain extraction.

[POS]
- HTTP API layer for inspectable workflow handoff & pipeline integrity Doctor pack.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Path, status

from app.schemas.pipeline_integrity import (
    AutoHealPipelineRequest,
    InspectDecisionChainRequest,
    LintPipelineRequest,
)
from app.schemas.responses import StandardSuccessResponse, create_success_response
from app.services.agent.pipeline_integrity_service import PipelineIntegrityService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Pipeline Integrity & Handoff Gap Doctor"])


def get_service() -> PipelineIntegrityService:
    """Dependency injector for PipelineIntegrityService."""
    return PipelineIntegrityService.get_instance()


@router.post(
    "/agents/pipeline-integrity/lint",
    response_model=StandardSuccessResponse,
    status_code=status.HTTP_200_OK,
    summary="Lint pipeline for handoff gaps and integrity issues",
)
async def lint_pipeline(
    request: LintPipelineRequest,
    service: PipelineIntegrityService = Depends(get_service),
) -> StandardSuccessResponse:
    """Inspect provided pipeline definition and generate a Doctor gap diagnosis report."""
    logger.info("Linting pipeline definition: %s", request.pipeline.pipeline_id)
    report = service.lint_pipeline(request.pipeline)
    return create_success_response(data=report.model_dump())


@router.post(
    "/agents/pipeline-integrity/auto-heal",
    response_model=StandardSuccessResponse,
    status_code=status.HTTP_200_OK,
    summary="Automatically heal detected pipeline integrity gaps",
)
async def auto_heal_pipeline(
    request: AutoHealPipelineRequest,
    service: PipelineIntegrityService = Depends(get_service),
) -> StandardSuccessResponse:
    """Auto-heal diagnosed gaps (handoff metadata, approval gates, verification steps)."""
    logger.info("Auto-healing pipeline definition: %s", request.pipeline.pipeline_id)
    healed = service.auto_heal_pipeline(request.pipeline)
    return create_success_response(data=healed.model_dump())


@router.post(
    "/agents/pipeline-integrity/inspect-chain",
    response_model=StandardSuccessResponse,
    status_code=status.HTTP_200_OK,
    summary="Extract transparent delegation decision chain",
)
async def inspect_decision_chain(
    request: InspectDecisionChainRequest,
    service: PipelineIntegrityService = Depends(get_service),
) -> StandardSuccessResponse:
    """Extract inspectable decision chain across step transitions."""
    chain = service.inspect_decision_chain(request.steps)
    return create_success_response(data=[link.model_dump() for link in chain])


@router.get(
    "/agents/pipeline-integrity/samples",
    response_model=StandardSuccessResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve predefined sample pipelines",
)
async def get_sample_pipelines(
    service: PipelineIntegrityService = Depends(get_service),
) -> StandardSuccessResponse:
    """Retrieve sample pipelines representing healthy and gapped setups."""
    samples = service.get_sample_pipelines()
    return create_success_response(data={k: v.model_dump() for k, v in samples.items()})


@router.get(
    "/agents/pipeline-integrity/reports/{pipeline_id}",
    response_model=StandardSuccessResponse,
    status_code=status.HTTP_200_OK,
    summary="Get cached latest diagnostic report for a pipeline",
)
async def get_latest_report(
    pipeline_id: str = Path(..., description="Pipeline identifier to query"),
    service: PipelineIntegrityService = Depends(get_service),
) -> StandardSuccessResponse:
    """Retrieve most recent diagnostic report for a pipeline if available."""
    report = service.get_latest_report(pipeline_id)
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No cached diagnostic report found for pipeline '{pipeline_id}'",
        )
    return create_success_response(data=report.model_dump())
