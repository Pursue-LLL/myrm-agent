"""FastAPI router for High-Concurrency Swarm & Adaptive Cloud Offload (Item 60).

[INPUT]
- app.schemas.swarm_offload::{
    SwarmDispatchBatchRequest, HostWatermarkReportRequest, OffloadPolicyUpdateRequest,
  }
- app.services.agent.swarm_offload_service::{
    SwarmOffloadService, get_swarm_offload_service,
  }

[OUTPUT]
- REST endpoints under /agents/swarm-offload for 10-15 subagent batch dispatch,
  host resource telemetry monitoring, and offloading policy management.

[POS]
- HTTP API layer for Item 60 preventing laptop physical saturation via cloud offloading.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status

from app.schemas.responses import StandardSuccessResponse, create_success_response
from app.schemas.swarm_offload import (
    HostWatermarkReportRequest,
    OffloadPolicyUpdateRequest,
    SwarmDispatchBatchRequest,
)
from app.services.agent.swarm_offload_service import (
    SwarmOffloadService,
    get_swarm_offload_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/agents/swarm-offload",
    tags=["High-Concurrency Subagent Swarm & Adaptive Cloud Offload"],
)


@router.post(
    "/dispatch",
    response_model=StandardSuccessResponse,
    status_code=status.HTTP_200_OK,
    summary="Dispatch a high-concurrency swarm batch with adaptive cloud offload",
)
async def dispatch_swarm_batch(
    req: SwarmDispatchBatchRequest,
    service: SwarmOffloadService = Depends(get_swarm_offload_service),
) -> StandardSuccessResponse:
    """Dispatch 10-15 tasks concurrently across local host and cloud sandboxes."""
    res = await service.dispatch_batch(req)
    return create_success_response(data=res.model_dump())


@router.get(
    "/batches/{batch_id}",
    response_model=StandardSuccessResponse,
    status_code=status.HTTP_200_OK,
    summary="Get aggregated outcome and worker records of a swarm batch",
)
async def get_swarm_batch(
    batch_id: str,
    service: SwarmOffloadService = Depends(get_swarm_offload_service),
) -> StandardSuccessResponse:
    """Lookup execution results and zero-copy artifact pointers for a batch."""
    batch = service.get_batch(batch_id)
    if not batch:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Swarm batch {batch_id} not found.",
        )
    return create_success_response(data=batch.model_dump())


@router.get(
    "/watermark",
    response_model=StandardSuccessResponse,
    status_code=status.HTTP_200_OK,
    summary="Get current host physical resource watermark and offload recommendation",
)
async def get_resource_watermark(
    service: SwarmOffloadService = Depends(get_swarm_offload_service),
) -> StandardSuccessResponse:
    """Fetch real-time snapshot of CPU, memory, and local worker load."""
    wm = service.get_current_watermark()
    return create_success_response(data=wm.model_dump())


@router.post(
    "/watermark/report",
    response_model=StandardSuccessResponse,
    status_code=status.HTTP_200_OK,
    summary="Report host CPU and memory usage from local desktop probe",
)
async def report_host_watermark(
    req: HostWatermarkReportRequest,
    service: SwarmOffloadService = Depends(get_swarm_offload_service),
) -> StandardSuccessResponse:
    """Update host physical metrics to govern adaptive cloud offloading."""
    wm = service.report_host_watermark(
        cpu_percent=req.cpu_percent,
        memory_percent=req.memory_percent,
    )
    return create_success_response(data=wm.model_dump())


@router.post(
    "/policy",
    response_model=StandardSuccessResponse,
    status_code=status.HTTP_200_OK,
    summary="Update global offloading strategy",
)
async def update_offload_policy(
    req: OffloadPolicyUpdateRequest,
    service: SwarmOffloadService = Depends(get_swarm_offload_service),
) -> StandardSuccessResponse:
    """Configure whether swarm tasks prefer adaptive offload, force local, or force cloud."""
    strat = service.update_policy(req)
    return create_success_response(data={"strategy": strat.value})

