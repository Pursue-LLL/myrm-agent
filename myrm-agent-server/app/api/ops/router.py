"""Ops Aggregated Snapshot API Router.

[INPUT]
- app.services.ops.snapshot_service::OpsAggregatedSnapshotService (POS: 快照聚合服务)
- app.schemas.ops::OpsAggregatedSnapshot (POS: 快照响应模型)

[OUTPUT]
- router: GET /api/v1/ops/snapshot

[POS]
提供统一的 Ops 运行态聚合快照接口，支持控制平面秒级舰队巡检、终端运维排障及前端一键状态大盘导出。
"""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.schemas.ops import OpsAggregatedSnapshot
from app.services.ops.snapshot_service import OpsAggregatedSnapshotService

router = APIRouter(prefix="/ops", tags=["Operations"])


@router.get(
    "/snapshot",
    response_model=OpsAggregatedSnapshot,
    summary="Get unified Ops aggregated operational snapshot",
    description=(
        "Returns a comprehensive operational snapshot of the single-agent runtime, "
        "aggregating system info, liveness, resources/RSS, channels, governance, "
        "usage radar, memory, and optional doctor health diagnostics in a single low-latency call."
    ),
)
async def get_ops_snapshot(
    include_doctor: bool = Query(
        default=True,
        description="Whether to include full Doctor component diagnostics (set to false for lightweight sub-5ms fleet polling)",
    ),
) -> OpsAggregatedSnapshot:
    """Collect full or lightweight operational snapshot."""
    return await OpsAggregatedSnapshotService.collect_snapshot(
        include_doctor=include_doctor
    )
