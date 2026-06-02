"""
[INPUT]
- app.database.models::CalendarEventModel (POS: 日历事件域模型)
- app.database.connection::get_session (POS: 数据库连接管理)

[OUTPUT]
- router: 日历事件 REST 路由（CRUD + 时间范围查询）

[POS]
日历事件 REST 接口层。提供日历事件的创建、查询、更新、删除和时间范围检索。
"""

import logging
import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import delete, select

from app.database.connection import get_session
from app.database.models import CalendarEventModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/calendar", tags=["Calendar"])


# ====================== Schemas ======================


class CalendarEventCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)
    description: str = ""
    location: str | None = None
    start_at: datetime
    end_at: datetime | None = None
    all_day: bool = False
    rrule: str | None = None
    color: str | None = None
    source: str = "manual"
    agent_id: str | None = None
    chat_id: str | None = None
    reminder_minutes: int | None = None
    status: str = "confirmed"


class CalendarEventUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    location: str | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None
    all_day: bool | None = None
    rrule: str | None = None
    color: str | None = None
    reminder_minutes: int | None = None
    status: str | None = None


class CalendarEventResponse(BaseModel):
    id: str
    title: str
    description: str
    location: str | None
    start_at: datetime
    end_at: datetime | None
    all_day: bool
    rrule: str | None
    color: str | None
    source: str
    agent_id: str | None
    chat_id: str | None
    reminder_minutes: int | None
    status: str
    created_at: datetime
    updated_at: datetime


class CalendarEventListResponse(BaseModel):
    items: list[CalendarEventResponse]
    total: int


# ====================== Helpers ======================


def _to_response(event: CalendarEventModel) -> CalendarEventResponse:
    return CalendarEventResponse(
        id=event.id,
        title=event.title,
        description=event.description,
        location=event.location,
        start_at=event.start_at,
        end_at=event.end_at,
        all_day=event.all_day,
        rrule=event.rrule,
        color=event.color,
        source=event.source,
        agent_id=event.agent_id,
        chat_id=event.chat_id,
        reminder_minutes=event.reminder_minutes,
        status=event.status,
        created_at=event.created_at,
        updated_at=event.updated_at,
    )


# ====================== Routes ======================


@router.post("", response_model=CalendarEventResponse)
async def create_event(body: CalendarEventCreate) -> CalendarEventResponse:
    """Create a new calendar event."""
    async with get_session() as session:
        event = CalendarEventModel(
            id=uuid.uuid4().hex[:32],
            title=body.title,
            description=body.description,
            location=body.location,
            start_at=body.start_at,
            end_at=body.end_at,
            all_day=body.all_day,
            rrule=body.rrule,
            color=body.color,
            source=body.source,
            agent_id=body.agent_id,
            chat_id=body.chat_id,
            reminder_minutes=body.reminder_minutes,
            status=body.status,
        )
        session.add(event)
        await session.commit()
        await session.refresh(event)
        return _to_response(event)


@router.get("", response_model=CalendarEventListResponse)
async def list_events(
    start: datetime | None = Query(None, description="Filter events starting after this time"),
    end: datetime | None = Query(None, description="Filter events starting before this time"),
    status: str | None = Query(None, description="Filter by status"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> CalendarEventListResponse:
    """List calendar events with optional time range and status filters."""
    async with get_session() as session:
        stmt = select(CalendarEventModel)
        count_stmt = select(CalendarEventModel)

        if start is not None:
            stmt = stmt.where(CalendarEventModel.start_at >= start)
            count_stmt = count_stmt.where(CalendarEventModel.start_at >= start)
        if end is not None:
            stmt = stmt.where(CalendarEventModel.start_at <= end)
            count_stmt = count_stmt.where(CalendarEventModel.start_at <= end)
        if status is not None:
            stmt = stmt.where(CalendarEventModel.status == status)
            count_stmt = count_stmt.where(CalendarEventModel.status == status)

        from sqlalchemy import func

        total = await session.scalar(select(func.count()).select_from(count_stmt.subquery()))

        stmt = stmt.order_by(CalendarEventModel.start_at.asc()).offset(offset).limit(limit)
        result = await session.execute(stmt)
        events = result.scalars().all()

        return CalendarEventListResponse(
            items=[_to_response(e) for e in events],
            total=total or 0,
        )


@router.get("/{event_id}", response_model=CalendarEventResponse)
async def get_event(event_id: str) -> CalendarEventResponse:
    """Get a single calendar event by ID."""
    async with get_session() as session:
        event = await session.get(CalendarEventModel, event_id)
        if not event:
            raise HTTPException(status_code=404, detail="Calendar event not found")
        return _to_response(event)


@router.patch("/{event_id}", response_model=CalendarEventResponse)
async def update_event(event_id: str, body: CalendarEventUpdate) -> CalendarEventResponse:
    """Update a calendar event."""
    async with get_session() as session:
        event = await session.get(CalendarEventModel, event_id)
        if not event:
            raise HTTPException(status_code=404, detail="Calendar event not found")

        update_data = body.model_dump(exclude_unset=True)
        if not update_data:
            raise HTTPException(status_code=400, detail="No fields to update")

        for field, value in update_data.items():
            setattr(event, field, value)

        await session.commit()
        await session.refresh(event)
        return _to_response(event)


@router.delete("/{event_id}")
async def delete_event(event_id: str) -> dict[str, str]:
    """Delete a calendar event."""
    async with get_session() as session:
        stmt = delete(CalendarEventModel).where(CalendarEventModel.id == event_id)
        result = await session.execute(stmt)
        await session.commit()
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Calendar event not found")
    return {"status": "ok"}
