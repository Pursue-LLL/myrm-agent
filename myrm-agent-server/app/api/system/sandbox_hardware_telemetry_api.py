"""
[INPUT]: Sandbox dynamic hardware metric telemetry readings and circuit breaker thresholds.
[OUTPUT]: Pydantic schemas and REST endpoints for sandbox hardware telemetry and three-tier runaway circuit breaking.
[POS]: myrm-agent/myrm-agent-server/app/api/system/sandbox_hardware_telemetry_api.py
"""

from typing import Dict, List, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from myrm_agent_harness.observability.sandbox_hardware_telemetry import (
    CircuitBreakerConfig,
    CircuitBreakerEvaluation,
    CircuitBreakerLevel,
    HardwareMetricSample,
    HardwareTelemetrySnapshot,
    get_default_hardware_circuit_breaker,
)

router = APIRouter(prefix="/sandbox-hardware", tags=["sandbox-hardware"])


# --- Pydantic Request & Response Schemas ---


class IngestSampleRequest(BaseModel):
    cpu_percent: float = Field(..., ge=0.0, le=100.0, description="CPU usage percentage")
    memory_used_bytes: int = Field(..., ge=0, description="Physical memory used in bytes")
    memory_total_bytes: int = Field(..., ge=1, description="Total physical memory in bytes")
    memory_percent: float = Field(..., ge=0.0, le=100.0, description="Memory usage percentage")
    disk_used_bytes: int = Field(default=0, ge=0, description="Disk volume used in bytes")
    disk_total_bytes: int = Field(default=107374182400, ge=1, description="Total disk capacity in bytes")
    disk_percent: float = Field(default=0.0, ge=0.0, le=100.0, description="Disk usage percentage")
    network_bytes_sent: int = Field(default=0, ge=0, description="Network bytes transmitted")
    network_bytes_recv: int = Field(default=0, ge=0, description="Network bytes received")


class ConfigureThresholdsRequest(BaseModel):
    warning_cpu_threshold: Optional[float] = Field(default=None, ge=1.0, le=100.0)
    suspend_cpu_threshold: Optional[float] = Field(default=None, ge=1.0, le=100.0)
    trip_cpu_threshold: Optional[float] = Field(default=None, ge=1.0, le=100.0)
    warning_mem_threshold: Optional[float] = Field(default=None, ge=1.0, le=100.0)
    suspend_mem_threshold: Optional[float] = Field(default=None, ge=1.0, le=100.0)
    trip_mem_threshold: Optional[float] = Field(default=None, ge=1.0, le=100.0)
    max_consecutive_violations: Optional[int] = Field(default=None, ge=1, le=20)
    max_task_duration_seconds: Optional[float] = Field(default=None, ge=10.0, le=86400.0)


class HardwareMetricSampleModel(BaseModel):
    cpu_percent: float
    memory_used_bytes: int
    memory_total_bytes: int
    memory_percent: float
    disk_used_bytes: int
    disk_total_bytes: int
    disk_percent: float
    network_bytes_sent: int
    network_bytes_recv: int
    timestamp_ms: int


class CircuitBreakerConfigModel(BaseModel):
    warning_cpu_threshold: float
    suspend_cpu_threshold: float
    trip_cpu_threshold: float
    warning_mem_threshold: float
    suspend_mem_threshold: float
    trip_mem_threshold: float
    max_consecutive_violations: int
    max_task_duration_seconds: float


class CircuitBreakerEvaluationModel(BaseModel):
    level: str
    triggered_metric: str
    current_value: float
    threshold_value: float
    action_description: str
    sample: HardwareMetricSampleModel
    evaluated_at_ms: int


class HardwareTelemetrySnapshotModel(BaseModel):
    latest_sample: Optional[HardwareMetricSampleModel]
    current_level: str
    config: CircuitBreakerConfigModel
    consecutive_violations: int
    incident_history: List[CircuitBreakerEvaluationModel]
    generated_at_ms: int


# --- Helper Converters ---


def _to_sample_model(s: HardwareMetricSample) -> HardwareMetricSampleModel:
    return HardwareMetricSampleModel(
        cpu_percent=round(s.cpu_percent, 2),
        memory_used_bytes=s.memory_used_bytes,
        memory_total_bytes=s.memory_total_bytes,
        memory_percent=round(s.memory_percent, 2),
        disk_used_bytes=s.disk_used_bytes,
        disk_total_bytes=s.disk_total_bytes,
        disk_percent=round(s.disk_percent, 2),
        network_bytes_sent=s.network_bytes_sent,
        network_bytes_recv=s.network_bytes_recv,
        timestamp_ms=s.timestamp_ms,
    )


def _to_config_model(c: CircuitBreakerConfig) -> CircuitBreakerConfigModel:
    return CircuitBreakerConfigModel(
        warning_cpu_threshold=c.warning_cpu_threshold,
        suspend_cpu_threshold=c.suspend_cpu_threshold,
        trip_cpu_threshold=c.trip_cpu_threshold,
        warning_mem_threshold=c.warning_mem_threshold,
        suspend_mem_threshold=c.suspend_mem_threshold,
        trip_mem_threshold=c.trip_mem_threshold,
        max_consecutive_violations=c.max_consecutive_violations,
        max_task_duration_seconds=c.max_task_duration_seconds,
    )


def _to_eval_model(ev: CircuitBreakerEvaluation) -> CircuitBreakerEvaluationModel:
    return CircuitBreakerEvaluationModel(
        level=ev.level.value,
        triggered_metric=ev.triggered_metric,
        current_value=round(ev.current_value, 2),
        threshold_value=round(ev.threshold_value, 2),
        action_description=ev.action_description,
        sample=_to_sample_model(ev.sample),
        evaluated_at_ms=ev.evaluated_at_ms,
    )


def _to_snapshot_model(snap: HardwareTelemetrySnapshot) -> HardwareTelemetrySnapshotModel:
    return HardwareTelemetrySnapshotModel(
        latest_sample=_to_sample_model(snap.latest_sample) if snap.latest_sample else None,
        current_level=snap.current_level.value,
        config=_to_config_model(snap.config),
        consecutive_violations=snap.consecutive_violations,
        incident_history=[_to_eval_model(i) for i in snap.incident_history],
        generated_at_ms=snap.generated_at_ms,
    )


# --- Endpoints ---


@router.post("/sample", response_model=CircuitBreakerEvaluationModel)
async def ingest_hardware_sample(req: IngestSampleRequest) -> CircuitBreakerEvaluationModel:
    """Ingest a hardware usage reading and evaluate against 3-tier circuit breaker thresholds."""
    breaker = get_default_hardware_circuit_breaker()
    sample = HardwareMetricSample(
        cpu_percent=req.cpu_percent,
        memory_used_bytes=req.memory_used_bytes,
        memory_total_bytes=req.memory_total_bytes,
        memory_percent=req.memory_percent,
        disk_used_bytes=req.disk_used_bytes,
        disk_total_bytes=req.disk_total_bytes,
        disk_percent=req.disk_percent,
        network_bytes_sent=req.network_bytes_sent,
        network_bytes_recv=req.network_bytes_recv,
    )
    evaluation = breaker.record_metric_sample(sample)
    return _to_eval_model(evaluation)


@router.get("/snapshot", response_model=HardwareTelemetrySnapshotModel)
async def get_hardware_snapshot() -> HardwareTelemetrySnapshotModel:
    """Retrieve atomic telemetry state snapshot for observability dashboards."""
    breaker = get_default_hardware_circuit_breaker()
    snapshot = breaker.get_snapshot()
    return _to_snapshot_model(snapshot)


@router.post("/configure", response_model=CircuitBreakerConfigModel)
async def configure_thresholds(req: ConfigureThresholdsRequest) -> CircuitBreakerConfigModel:
    """Adjust three-tier laddered thresholds and maximum execution limits."""
    breaker = get_default_hardware_circuit_breaker()
    curr = breaker.config
    updated = CircuitBreakerConfig(
        warning_cpu_threshold=req.warning_cpu_threshold if req.warning_cpu_threshold is not None else curr.warning_cpu_threshold,
        suspend_cpu_threshold=req.suspend_cpu_threshold if req.suspend_cpu_threshold is not None else curr.suspend_cpu_threshold,
        trip_cpu_threshold=req.trip_cpu_threshold if req.trip_cpu_threshold is not None else curr.trip_cpu_threshold,
        warning_mem_threshold=req.warning_mem_threshold if req.warning_mem_threshold is not None else curr.warning_mem_threshold,
        suspend_mem_threshold=req.suspend_mem_threshold if req.suspend_mem_threshold is not None else curr.suspend_mem_threshold,
        trip_mem_threshold=req.trip_mem_threshold if req.trip_mem_threshold is not None else curr.trip_mem_threshold,
        max_consecutive_violations=req.max_consecutive_violations if req.max_consecutive_violations is not None else curr.max_consecutive_violations,
        max_task_duration_seconds=req.max_task_duration_seconds if req.max_task_duration_seconds is not None else curr.max_task_duration_seconds,
    )
    breaker.update_config(updated)
    return _to_config_model(updated)


@router.post("/reset")
async def reset_circuit_breaker() -> Dict[str, bool]:
    """Reset circuit breaker state to NORMAL and clear historical incident logs."""
    breaker = get_default_hardware_circuit_breaker()
    breaker.reset()
    return {"ok": True}
