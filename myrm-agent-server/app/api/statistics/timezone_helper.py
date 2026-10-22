"""Timezone resolution and conversion helper for statistics endpoints.

[INPUT]
- query_tz / header_tz: Optional timezone identifier strings from clients
- dt: datetime instances from database or timestamps

[OUTPUT]
- resolve_user_timezone: (tzinfo, str) pair with safe fallback to UTC
- to_user_local_dt: timezone-aware datetime converted to user target timezone

[POS]
- app/api/statistics/timezone_helper.py: Common timezone utilities for statistics endpoints
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

logger = logging.getLogger(__name__)


def resolve_user_timezone(
    query_tz: str | None = None,
    header_tz: str | None = None,
) -> tuple[tzinfo, str]:
    """Resolve user timezone from Query parameter or HTTP Header with fallback to UTC.

    Priority:
    1. query_tz (explicit query string argument)
    2. header_tz (X-Timezone request header)
    3. Fallback: UTC (never fall back to server system local time).

    Returns:
        tuple[tzinfo, str]: The resolved tzinfo object and canonical timezone string name.
    """
    candidate = query_tz or header_tz
    if not candidate or not candidate.strip():
        return UTC, "UTC"

    cleaned = candidate.strip()
    try:
        return ZoneInfo(cleaned), cleaned
    except (ZoneInfoNotFoundError, ValueError, TypeError) as exc:
        logger.warning("Unrecognized timezone '%s', falling back to UTC: %s", cleaned, exc)
        return UTC, "UTC"


def to_user_local_dt(dt: datetime | None, user_tz: tzinfo) -> datetime | None:
    """Convert naive or aware datetime to user target timezone."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(user_tz)
