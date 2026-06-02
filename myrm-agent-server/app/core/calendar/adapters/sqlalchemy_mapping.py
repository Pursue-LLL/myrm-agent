"""ORM <-> Domain mapping for calendar models.

Bidirectional conversion between SQLAlchemy ORM models and
framework domain objects (CalendarEvent).
"""

from __future__ import annotations

from myrm_agent_harness.toolkits.calendar.types import CalendarEvent

from app.database.models.calendar_event import CalendarEventModel


def event_to_domain(m: CalendarEventModel) -> CalendarEvent:
    """Convert ORM model to domain type."""
    return CalendarEvent(
        event_id=m.id,
        title=m.title,
        description=m.description,
        location=m.location,
        start_at=m.start_at,
        end_at=m.end_at,
        all_day=m.all_day,
        rrule=m.rrule,
        color=m.color,
        source=m.source,
        agent_id=m.agent_id,
        chat_id=m.chat_id,
        reminder_minutes=m.reminder_minutes,
        status=m.status,
        created_at=m.created_at,
        updated_at=m.updated_at,
    )


def event_to_model(e: CalendarEvent) -> CalendarEventModel:
    """Convert domain type to ORM model (for creation)."""
    return CalendarEventModel(
        id=e.event_id,
        title=e.title,
        description=e.description,
        location=e.location,
        start_at=e.start_at,
        end_at=e.end_at,
        all_day=e.all_day,
        rrule=e.rrule,
        color=e.color,
        source=e.source,
        agent_id=e.agent_id,
        chat_id=e.chat_id,
        reminder_minutes=e.reminder_minutes,
        status=e.status,
    )


def apply_event_to_model(e: CalendarEvent, m: CalendarEventModel) -> None:
    """Apply domain changes to existing ORM model (for update)."""
    m.title = e.title
    m.description = e.description
    m.location = e.location
    m.start_at = e.start_at
    m.end_at = e.end_at
    m.all_day = e.all_day
    m.rrule = e.rrule
    m.color = e.color
    m.source = e.source
    m.agent_id = e.agent_id
    m.chat_id = e.chat_id
    m.reminder_minutes = e.reminder_minutes
    m.status = e.status
