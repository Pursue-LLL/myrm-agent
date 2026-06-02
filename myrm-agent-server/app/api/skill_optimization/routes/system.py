from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from myrm_agent_harness.agent.skills.optimization.health_check import AggregatedHealthResult
from myrm_agent_harness.agent.skills.optimization.scheduler import OptimizationScheduler

from app.adapters.skill_optimization.sqlalchemy_storage import SQLAlchemyStorage
from app.api.skill_optimization.dependencies import (
    get_scheduler,
    get_storage,
)

router = APIRouter()

@router.get("/health")
async def get_health_status(
    scheduler: Annotated[OptimizationScheduler, Depends(get_scheduler)],
    storage: Annotated[SQLAlchemyStorage, Depends(get_storage)],
) -> AggregatedHealthResult:
    """健康检查API，返回scheduler和storage的健康状态。"""
    from myrm_agent_harness.agent.skills.optimization.health_check import aggregate_health_checks

    health_result = await aggregate_health_checks(
        {
            "scheduler": scheduler,
            "storage": storage,
        },
        strict=True,
    )

    return health_result

@router.get("/metrics")
async def get_prometheus_metrics(
    scheduler: Annotated[OptimizationScheduler, Depends(get_scheduler)],
) -> dict[str, object]:
    """Prometheus Metrics导出API。"""
    metrics = scheduler.get_metrics()

    return {
        "metrics": metrics,
        "format": "prometheus",
    }

