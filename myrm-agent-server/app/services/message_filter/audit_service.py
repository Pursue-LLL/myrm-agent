"""Audit service for message filtering events.

Provides persistent storage of filter events to database for security monitoring.
"""

import logging
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import MessageFilterAudit

logger = logging.getLogger(__name__)


class AuditService:
    """Service for recording and querying message filter audit logs.

    Usage:
        >>> async with get_session() as db:
        ...     audit = AuditService(db)
        ...     await audit.log_event(
        ...         ...         filter_type="SystemRoleFilter",
        ...         action="MESSAGE_FILTERED",
        ...         reason="System role message filtered",
        ...         metadata={"role": "system"}
        ...     )
        ...     logs = await audit.get_logs(limit=10)
    """

    def __init__(self, db_session: AsyncSession):
        self._db = db_session

    async def log_event(
        self,
        filter_type: str,
        action: str,
        reason: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> MessageFilterAudit:
        """Record a filter event to the audit log.

        Args:
            filter_type: Name of the filter (e.g., "SystemRoleFilter", "PIIRedactionFilter")
            action: Action taken (e.g., "MESSAGE_FILTERED", "PII_REDACTED", "CREDENTIAL_LEAK_BLOCKED")
            reason: Human-readable reason for the action
            metadata: Additional context (e.g., {"role": "system", "message_id": "123"})

        Returns:
            Created audit log entry
        """
        entry = MessageFilterAudit(
            filter_type=filter_type,
            action=action,
            reason=reason,
            metadata=metadata or {},
        )
        self._db.add(entry)
        await self._db.flush()
        logger.debug(f"Audit log: {filter_type} - {action} ")
        return entry

    async def get_logs(
        self,
        filter_type: str | None = None,
        action: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[MessageFilterAudit]:
        """Query audit logs with filters.

        Args:
            filter_type: Filter by filter type (optional)
            action: Filter by action (optional)
            limit: Maximum number of entries to return
            offset: Number of entries to skip (for pagination)

        Returns:
            List of matching audit log entries, newest first
        """
        stmt = select(MessageFilterAudit).order_by(desc(MessageFilterAudit.timestamp))
        if filter_type:
            stmt = stmt.where(MessageFilterAudit.filter_type == filter_type)
        if action:
            stmt = stmt.where(MessageFilterAudit.action == action)

        stmt = stmt.limit(limit).offset(offset)
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def get_stats(self, filter_type: str | None = None) -> dict[str, Any]:
        """Get aggregated statistics from audit logs.

        Args:
            filter_type: Filter by filter type (optional)

        Returns:
            Dictionary with stats: total_events, events_by_action, events_by_filter
        """
        from sqlalchemy import func

        stmt = select(
            MessageFilterAudit.action,
            MessageFilterAudit.filter_type,
            func.count().label("count"),
        ).group_by(MessageFilterAudit.action, MessageFilterAudit.filter_type)
        if filter_type:
            stmt = stmt.where(MessageFilterAudit.filter_type == filter_type)

        result = await self._db.execute(stmt)
        rows = result.all()

        events_by_action: dict[str, int] = {}
        events_by_filter: dict[str, int] = {}
        total_events = 0

        for row in rows:
            action, ftype, count = row
            total_events += count
            events_by_action[action] = events_by_action.get(action, 0) + count
            events_by_filter[ftype] = events_by_filter.get(ftype, 0) + count

        return {
            "total_events": total_events,
            "events_by_action": events_by_action,
            "events_by_filter": events_by_filter,
        }
