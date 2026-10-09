"""FastAPI router for screen observation memory safety, anti-injection, and promotion gate.

[POS]
屏幕与桌面观测型记忆防注入边界、强制描述性事实抽取与防过度泛化门禁 HTTP 接入层 (Topic 01 Item 85)。
暴露观测证据接入、防注入扫描、语法校验、多会话频次门禁与审计日志查询端点。

[INPUT]
- app.schemas.screen_observation_safety DTOs
- app.services.memory.screen_observation_safety_service::get_screen_observation_safety_service

[OUTPUT]
- router: Screen observation safety REST 路由
"""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.schemas.screen_observation_safety import (
    IngestScreenObservationRequest,
    ScreenObservationSafetyResponse,
    ScreenSafetyAuditListResponse,
)
from app.services.memory.screen_observation_safety_service import (
    get_screen_observation_safety_service,
)

router = APIRouter(prefix="/screen-observation", tags=["memory-screen-observation-safety"])


@router.post(
    "/process",
    response_model=ScreenObservationSafetyResponse,
    summary="Process raw screen observation evidence through anti-injection and descriptive fact gate",
)
def process_observation(
    request: IngestScreenObservationRequest,
) -> ScreenObservationSafetyResponse:
    """Ingest raw screen observation text, apply Skysight-style anti-injection fence,

    validate third-person descriptive syntax, and evaluate promotion gate status.
    """
    service = get_screen_observation_safety_service()
    return service.process_observation(request)


@router.get(
    "/audit-records",
    response_model=ScreenSafetyAuditListResponse,
    summary="Retrieve recent screen observation safety and gatekeeper audit ledger records",
)
def get_audit_records(
    limit: int = Query(default=50, ge=1, le=200, description="Maximum audit records to return"),
) -> ScreenSafetyAuditListResponse:
    """Query recent screen observation safety audit ledger."""
    service = get_screen_observation_safety_service()
    return service.get_audit_records(limit=limit)
