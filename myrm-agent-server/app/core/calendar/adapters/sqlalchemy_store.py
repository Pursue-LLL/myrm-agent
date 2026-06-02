"""SQLAlchemy implementation of the CalendarStore protocol.

CRUD operations for calendar events.
ORM mapping is delegated to ``sqlalchemy_mapping``.
"""

from __future__ import annotations

from datetime import datetime

from myrm_agent_harness.toolkits.calendar.types import CalendarEvent
from sqlalchemy import delete, func, select

from app.core.calendar.adapters.sqlalchemy_mapping import (
    apply_event_to_model,
    event_to_domain,
    event_to_model,
)
from app.database.connection import get_session
from app.database.models.calendar_event import CalendarEventModel


class SqlAlchemyCalendarStore:
    """CalendarStore backed by SQLAlchemy + app.database models."""

    async def get_event(self, event_id: str) -> CalendarEvent | None:
        async with get_session() as session:
            m = await session.get(CalendarEventModel, event_id)
            return event_to_domain(m) if m else None

    async def list_events(
        self,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[CalendarEvent]:
        async with get_session() as session:
            stmt = select(CalendarEventModel)

            if start is not None:
                stmt = stmt.where(CalendarEventModel.start_at >= start)
            if end is not None:
                stmt = stmt.where(CalendarEventModel.start_at <= end)
            if status is not None:
                stmt = stmt.where(CalendarEventModel.status == status)

            stmt = stmt.order_by(CalendarEventModel.start_at.asc()).offset(offset).limit(limit)
            result = await session.execute(stmt)
            return [event_to_domain(m) for m in result.scalars().all()]

    async def count_events(
        self,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        status: str | None = None,
    ) -> int:
        async with get_session() as session:
            stmt = select(func.count()).select_from(CalendarEventModel)

            if start is not None:
                stmt = stmt.where(CalendarEventModel.start_at >= start)
            if end is not None:
                stmt = stmt.where(CalendarEventModel.start_at <= end)
            if status is not None:
                stmt = stmt.where(CalendarEventModel.status == status)

            result = await session.scalar(stmt)
            return result or 0

    async def save_event(self, event: CalendarEvent) -> CalendarEvent:
        async with get_session() as session:
            existing = await session.get(CalendarEventModel, event.event_id)
            if existing:
                apply_event_to_model(event, existing)
                await session.commit()
                await session.refresh(existing)
                return event_to_domain(existing)
            else:
                model = event_to_model(event)
                session.add(model)
                await session.commit()
                await session.refresh(model)
                return event_to_domain(model)

    async def delete_event(self, event_id: str) -> bool:
        async with get_session() as session:
            stmt = delete(CalendarEventModel).where(CalendarEventModel.id == event_id)
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount > 0

    async def get_free_busy(
        self,
        user_ids: list[str],
        start: datetime,
        end: datetime,
        **kwargs: object,
    ) -> list[dict[str, object]]:
        """Return free/busy information for a list of users.
        
        Currently implements local db lookups for simulation.
        If a real provider like Feishu is attached to kwargs, it could delegate there.
        """
        async with get_session() as session:
            all_results = []
            for uid in user_ids:
                stmt = select(CalendarEventModel).where(
                    CalendarEventModel.start_at < end,
                    CalendarEventModel.end_at > start,
                    CalendarEventModel.status == "confirmed"
                )
                # If your model stores users/attendees, filter by uid here.
                # Since CalendarEventModel may not have full user mapping in base,
                # we just return local conflicting events in this prototype.
                result = await session.execute(stmt)
                events = result.scalars().all()
                busy_slots = [
                    {"start": e.start_at.isoformat(), "end": e.end_at.isoformat()}
                    for e in events if e.start_at and e.end_at
                ]
                all_results.append({
                    "user_id": uid,
                    "busy_slots": busy_slots
                })
            return all_results
