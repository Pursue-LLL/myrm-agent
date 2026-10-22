"""
[INPUT]: Memory operation telemetry, recall phase metrics, backend labels, and opt-in settings.
[OUTPUT]: REST API endpoints for memory backend label performance metrics, phase latency breakdowns, and opt-in cardinality toggles.
[POS]: myrm-agent/myrm-agent-server/app/api/system/memory_backend_metrics_api.py
"""

from typing import Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from myrm_agent_harness.observability.memory_backend_metrics import (
    MemoryBackendKind,
    MemoryBackendMetricsRecorder,
    MemoryBackendMetricsReport,
    MemoryBackendPerformanceStats,
    MemoryOperationMetricSample,
    MemoryOperationType,
    RecallPhaseType,
)

router = APIRouter(prefix="/memory-backend-metrics", tags=["memory-backend-metrics"])

_default_recorder = MemoryBackendMetricsRecorder(opt_in_enabled=True)


def get_default_metrics_recorder() -> MemoryBackendMetricsRecorder:
    return _default_recorder


# --- Request & Response Models ---


class RecordMemorySampleRequest(BaseModel):
    backend: str = Field(..., description="sqlite_fts5 | qdrant | in_memory | external")
    operation: str = Field(..., description="retain | recall | consolidate")
    duration_ms: float = Field(..., ge=0.0)
    phase: str = Field(default="none", description="collect | fuse | rerank | none")
    success: bool = Field(default=True)
    degraded: bool = Field(default=False)
    timestamp_ms: Optional[int] = Field(default=None)


class ConfigureMetricsRequest(BaseModel):
    opt_in_enabled: bool = Field(..., description="Whether memories_backend label dimension is active")


# --- Endpoints ---


@router.post("/sample")
def record_memory_sample(req: RecordMemorySampleRequest) -> Dict[str, Optional[str]]:
    """Record a memory operation sample with backend dimension and recall phase."""
    try:
        backend_enum = MemoryBackendKind(req.backend.lower())
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid backend '{req.backend}'. Valid options: {[k.value for k in MemoryBackendKind]}",
        )

    try:
        op_enum = MemoryOperationType(req.operation.lower())
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid operation '{req.operation}'. Valid options: {[k.value for k in MemoryOperationType]}",
        )

    try:
        phase_enum = RecallPhaseType(req.phase.lower())
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid phase '{req.phase}'. Valid options: {[k.value for k in RecallPhaseType]}",
        )

    recorder = get_default_metrics_recorder()
    sample = recorder.record_sample(
        backend=backend_enum,
        operation=op_enum,
        duration_ms=req.duration_ms,
        phase=phase_enum,
        success=req.success,
        degraded=req.degraded,
        timestamp_ms=req.timestamp_ms,
    )
    return {
        "status": "recorded" if sample is not None else "dropped_opt_in_disabled",
        "sample_id": sample.sample_id if sample else None,
    }


@router.get("/report", response_model=MemoryBackendMetricsReport)
def get_metrics_report() -> MemoryBackendMetricsReport:
    """Retrieve aggregated P50/P95 latencies and degradation counts partitioned by backend and phase."""
    recorder = get_default_metrics_recorder()
    return recorder.get_report()


@router.post("/configure")
def configure_metrics(req: ConfigureMetricsRequest) -> Dict[str, bool]:
    """Toggle the opt-in high-cardinality memories_backend dimension."""
    recorder = get_default_metrics_recorder()
    recorder.configure(opt_in_enabled=req.opt_in_enabled)
    return {"opt_in_enabled": req.opt_in_enabled}


@router.post("/reset")
def reset_metrics() -> Dict[str, str]:
    """Reset all recorded memory operation metrics."""
    recorder = get_default_metrics_recorder()
    recorder.reset()
    return {"status": "reset_completed"}
