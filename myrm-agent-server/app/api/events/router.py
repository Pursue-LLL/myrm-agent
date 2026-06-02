"""Agent Events API Router

提供事件查询和实时推送接口，仅本地模式启用。
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db_session
from app.config.deploy_mode import is_local_mode
from app.services.event.turn_manager import TurnManager
from app.services.event.types import EventType, TurnStatus

router = APIRouter(prefix="/events")

# ============================================================================
# Schemas
# ============================================================================


class EventSchema(BaseModel):
    """事件响应 Schema"""

    id: str
    turn_id: str
    event_type: str
    level: str
    event_index: int
    payload: dict[str, object]
    tool_name: str | None = None
    file_path: str | None = None
    duration_ms: int | None = None
    created_at: datetime

    class Config:
        from_attributes = True


class TurnSchema(BaseModel):
    """Turn 响应 Schema"""

    id: str
    chat_id: str
    turn_index: int
    user_input: str | None = None
    status: str
    event_count: int
    tool_call_count: int
    error_count: int
    duration_ms: int | None = None
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None

    class Config:
        from_attributes = True


class TurnWithEventsSchema(TurnSchema):
    """包含事件的 Turn 响应 Schema"""

    events: list[EventSchema] = Field(default_factory=list)


class TurnListResponse(BaseModel):
    """Turn 列表响应"""

    turns: list[TurnSchema]
    total: int


class EventListResponse(BaseModel):
    """Event 列表响应"""

    events: list[EventSchema]
    total: int


class FeatureStatusResponse(BaseModel):
    """功能状态响应"""

    enabled: bool
    mode: str  # local / sandbox


# ============================================================================
# Helper
# ============================================================================


def require_local_mode() -> None:
    """检查是否为本地模式，否则返回 404"""
    if not is_local_mode():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="This feature is only available in local mode",
        )


# ============================================================================
# Routes
# ============================================================================


@router.get("/status", response_model=FeatureStatusResponse)
async def get_events_status() -> FeatureStatusResponse:
    """获取事件系统状态

    用于前端判断是否显示事件相关 UI。
    """
    return FeatureStatusResponse(
        enabled=is_local_mode(),
        mode="local" if is_local_mode() else "sandbox",
    )


@router.get("/turns", response_model=TurnListResponse)
async def get_turns(
    chat_id: str = Query(..., description="Chat ID"),
    limit: int = Query(50, ge=1, le=100, description="每页数量"),
    offset: int = Query(0, ge=0, description="偏移量"),
    db: AsyncSession = Depends(get_db_session),
) -> TurnListResponse:
    """获取 Chat 的所有 Turn

    仅本地模式可用。
    """
    require_local_mode()

    manager = TurnManager(db)
    turns = await manager.get_turns_by_chat(chat_id, limit=limit, offset=offset)

    return TurnListResponse(
        turns=[TurnSchema.model_validate(t) for t in turns],
        total=len(turns),
    )


@router.get("/turns/{turn_id}", response_model=TurnWithEventsSchema)
async def get_turn_with_events(
    turn_id: str,
    event_limit: int = Query(100, ge=1, le=500, description="事件数量限制"),
    db: AsyncSession = Depends(get_db_session),
) -> TurnWithEventsSchema:
    """获取单个 Turn 及其事件

    仅本地模式可用。
    """
    require_local_mode()

    manager = TurnManager(db)
    turn = await manager.get_turn(turn_id)

    if not turn:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Turn {turn_id} not found",
        )

    events = await manager.get_events_by_turn(turn_id, limit=event_limit)

    return TurnWithEventsSchema(
        **TurnSchema.model_validate(turn).model_dump(),
        events=[EventSchema.model_validate(e) for e in events],
    )


@router.get("/turns/{turn_id}/events", response_model=EventListResponse)
async def get_events_by_turn(
    turn_id: str,
    event_type: str | None = Query(None, description="事件类型过滤"),
    limit: int = Query(100, ge=1, le=500, description="每页数量"),
    offset: int = Query(0, ge=0, description="偏移量"),
    db: AsyncSession = Depends(get_db_session),
) -> EventListResponse:
    """获取 Turn 的事件列表

    支持按事件类型过滤。仅本地模式可用。
    """
    require_local_mode()

    manager = TurnManager(db)
    events = await manager.get_events_by_turn(turn_id, limit=limit, offset=offset)

    # 按类型过滤
    if event_type:
        events = [e for e in events if e.event_type == event_type]

    return EventListResponse(
        events=[EventSchema.model_validate(e) for e in events],
        total=len(events),
    )


@router.get("/event-types", response_model=list[str])
async def get_event_types() -> list[str]:
    """获取所有支持的事件类型

    用于前端构建过滤器。
    """
    return [e.value for e in EventType]


@router.get("/turn-statuses", response_model=list[str])
async def get_turn_statuses() -> list[str]:
    """获取所有 Turn 状态

    用于前端构建过滤器。
    """
    return [s.value for s in TurnStatus]
