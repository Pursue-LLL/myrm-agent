"""FastAPI router for Dream Cognitive Consolidation and Growth Diary API endpoints.

[POS]
后台梦境认知重组与智能体成长日记 REST API 路由。
暴露跨会话认知整合触发、心智演进日记检索、Markdown 具身视图渲染与空间概览统计。

[INPUT]
- POST /api/memory/dream-cognitive/consolidate
- GET /api/memory/dream-cognitive/diaries
- GET /api/memory/dream-cognitive/diaries/{diary_id}
- GET /api/memory/dream-cognitive/diaries/{diary_id}/markdown
- GET /api/memory/dream-cognitive/overview

[OUTPUT]
- 严格遵循 OpenAPI / Pydantic 响应契约的 JSON 与纯文本 Markdown 响应
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from app.schemas.dream_cognitive import (
    CognitiveConsolidationReportDTO,
    CognitiveConsolidationRequestDTO,
    DreamCognitiveOverviewDTO,
    GrowthDiaryEntryDTO,
)
from app.services.memory.dream_cognitive_service import (
    DreamCognitiveService,
    get_dream_cognitive_service,
)

router = APIRouter(prefix="/dream-cognitive", tags=["memory-dream-cognitive"])


@router.post(
    "/consolidate",
    response_model=CognitiveConsolidationReportDTO,
    status_code=status.HTTP_200_OK,
    summary="Trigger dream cognitive consolidation cycle",
)
def trigger_cognitive_consolidation(
    req: CognitiveConsolidationRequestDTO,
    service: DreamCognitiveService = Depends(get_dream_cognitive_service),
) -> CognitiveConsolidationReportDTO:
    """Execute background dreaming cycle across session fragments to extract higher-level insights."""
    return service.consolidate(req)


@router.get(
    "/diaries",
    response_model=list[GrowthDiaryEntryDTO],
    summary="List recorded growth diary entries",
)
def list_growth_diaries(
    cube_id: str | None = Query(default=None, description="Optional Memory Cube ID filter"),
    limit: int = Query(default=50, ge=1, le=200, description="Max entries to return"),
    service: DreamCognitiveService = Depends(get_dream_cognitive_service),
) -> list[GrowthDiaryEntryDTO]:
    """Retrieve human-readable AI embodiment growth diaries."""
    return service.list_diaries(cube_id=cube_id, limit=limit)


@router.get(
    "/diaries/{diary_id}",
    response_model=GrowthDiaryEntryDTO,
    summary="Get single growth diary entry",
)
def get_growth_diary(
    diary_id: str,
    service: DreamCognitiveService = Depends(get_dream_cognitive_service),
) -> GrowthDiaryEntryDTO:
    """Fetch details of a single growth diary entry."""
    entry = service.get_diary(diary_id)
    if entry is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Growth diary with id '{diary_id}' not found.",
        )
    return entry


@router.get(
    "/diaries/{diary_id}/markdown",
    summary="Get formatted markdown of growth diary entry",
)
def get_growth_diary_markdown(
    diary_id: str,
    service: DreamCognitiveService = Depends(get_dream_cognitive_service),
) -> Response:
    """Fetch the beautiful formatted markdown presentation for direct WebUI/Desktop display."""
    md_content = service.get_diary_markdown(diary_id)
    if md_content is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Growth diary with id '{diary_id}' not found.",
        )
    return Response(content=md_content, media_type="text/markdown; charset=utf-8")


@router.get(
    "/overview",
    response_model=DreamCognitiveOverviewDTO,
    summary="Get cognitive dreaming system overview",
)
def get_cognitive_overview(
    service: DreamCognitiveService = Depends(get_dream_cognitive_service),
) -> DreamCognitiveOverviewDTO:
    """Retrieve summary metrics and active cubes for dream cognitive evolution."""
    return service.get_overview()
