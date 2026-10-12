"""API router for Graph Memory Reorganization and Lineage Traceability endpoints.

[POS]
记忆图谱重组与演化溯源链 API 路由层。
提供图重组扫描、白盒 DAG 谱系追溯、版本回滚、全景拓扑与概览指标接口。

[INPUT]
- app.schemas.memory_lineage::(各类请求体与响应 DTO)
- app.services.memory.memory_lineage_service::memory_lineage_service

[OUTPUT]
- router: FastAPI APIRouter 实例，挂载于 /api/memory/lineage
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, status

from app.schemas.memory_lineage import (
    LineageRevertRequest,
    LineageRevertResponse,
    LineageStatsDTO,
    MemoryLineageTrailDTO,
    MemoryTopologyGraphDTO,
    ReorganizationBatchRequest,
    ReorganizationBatchResponse,
)
from app.services.memory.memory_lineage_service import memory_lineage_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/lineage", tags=["Memory Lineage & Graph Reorganization"])


@router.post(
    "/reorganize",
    response_model=ReorganizationBatchResponse,
    status_code=status.HTTP_200_OK,
    summary="Trigger graph memory reorganization and multi-relational edge synthesis",
)
async def trigger_reorganization(
    payload: ReorganizationBatchRequest,
) -> ReorganizationBatchResponse:
    """Execute an automated graph memory reorganization pass, inferring multi-relational semantic edges."""
    try:
        return memory_lineage_service.run_reorganization(
            min_confidence=payload.min_confidence,
        )
    except Exception as exc:
        logger.exception("Failed to execute memory graph reorganization: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Reorganization failed: {exc}",
        ) from exc


@router.get(
    "/trace/{node_id}",
    response_model=MemoryLineageTrailDTO,
    status_code=status.HTTP_200_OK,
    summary="Trace white-box lineage DAG trail for a specific memory node",
)
async def trace_node_lineage(
    node_id: str,
) -> MemoryLineageTrailDTO:
    """Retrieve the full explainable lineage evolution trajectory across ancestors, descendants, and steps."""
    try:
        return memory_lineage_service.trace_lineage(node_id=node_id)
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Target memory node '{node_id}' not found in lineage registry.",
        ) from exc
    except Exception as exc:
        logger.exception("Failed to trace lineage for node %s: %s", node_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Lineage trace failed: {exc}",
        ) from exc


@router.post(
    "/revert",
    response_model=LineageRevertResponse,
    status_code=status.HTTP_200_OK,
    summary="Revert an active memory state to a historical version snapshot",
)
async def revert_memory_version(
    payload: LineageRevertRequest,
) -> LineageRevertResponse:
    """Atomically spawn an active successor version restoring historical snapshot while preserving audit lineage."""
    try:
        return memory_lineage_service.revert_version(
            historical_node_id=payload.historical_node_id,
            rationale=payload.rationale,
        )
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Target historical node '{payload.historical_node_id}' not found.",
        ) from exc
    except Exception as exc:
        logger.exception("Failed to revert memory version: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Version reversion failed: {exc}",
        ) from exc


@router.get(
    "/topology",
    response_model=MemoryTopologyGraphDTO,
    status_code=status.HTTP_200_OK,
    summary="Retrieve full knowledge graph topology including nodes and relational edges",
)
async def get_graph_topology() -> MemoryTopologyGraphDTO:
    """Export memory nodes and relational edges for DAG visualization."""
    return memory_lineage_service.get_topology()


@router.get(
    "/stats",
    response_model=LineageStatsDTO,
    status_code=status.HTTP_200_OK,
    summary="Retrieve overall lineage statistics and graph health indicators",
)
async def get_lineage_stats() -> LineageStatsDTO:
    """Fetch total node counts, active vs superseded split, edge metrics, and max lineage depth."""
    return memory_lineage_service.get_stats()
