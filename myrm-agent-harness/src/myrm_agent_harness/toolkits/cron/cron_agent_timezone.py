"""Time zone contract of the ``cron_manage`` tool.

Every wall-clock input of a task is read in one zone: an ``at`` or ``expires_after`` without an offset, a cron
expression and the active-hours window. The zone is the explicit ``tz``, else the task's own zone when it is
being edited, else the requester's zone, else UTC. A time that carries its own offset keeps it.

[INPUT]
- core.context_vars::request_timezone (POS: 跨层 ContextVar，请求时区的校验后访问器)
- toolkits.cron.engine.parser::validate_timezone (POS: cron 表达式解析与下次运行时间计算)

[OUTPUT]
- resolve_timezone: explicit zone, else inherited, else the requester's, as (error, zone name or None for UTC)
- parse_local_datetime: ISO 8601 text to an aware datetime; a time without offset is read in the zone
- zone_fields: the ``timezone`` and ``next_run_local`` entries of a task's JSON result

[POS]
Time-zone half of the ``cron_manage`` tool. Pure functions apart from reading the request's zone, so the rules
(the zone chain, a daylight-saving gap, a repeated hour) can be tested without a ``CronManager``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from myrm_agent_harness.core.context_vars import request_timezone
from myrm_agent_harness.toolkits.cron.engine.parser import validate_timezone

_ISO_EXAMPLE = "'2026-03-01T10:00:00' or '2026-03-01T10:00:00+08:00'"


def resolve_timezone(explicit: str, *, inherited: str | None = None) -> tuple[str | None, str | None]:
    """Choose the zone a task's wall-clock inputs are read in: ``explicit``, else ``inherited``, else the request's.

    Returns ``(error, zone)``; ``zone`` is None when nothing names one, which means UTC. Only an explicit name can
    be an error: an unknown zone in the request is ignored, since the model did not choose it.
    """
    name = explicit.strip()
    if not name:
        return None, inherited or request_timezone()
    if not validate_timezone(name):
        return f"Unknown timezone '{name}'. Use an IANA name such as 'Asia/Shanghai' or 'America/New_York'.", None
    return None, name


def parse_local_datetime(text: str, zone: str | None) -> datetime:
    """Parse ISO 8601 *text* into an aware datetime; a time without an offset is read in *zone* (UTC when None).

    A repeated local time (clocks turned back) is the earlier of its two instants. Raises ``ValueError`` with a
    message for the model when *text* is not an ISO 8601 date-time or the local time does not exist in *zone*.
    """
    try:
        parsed = datetime.fromisoformat(text.strip())
    except ValueError:
        raise ValueError(f"not an ISO 8601 date-time; use {_ISO_EXAMPLE}") from None
    if parsed.tzinfo is not None:
        return parsed
    if zone is None:
        return parsed.replace(tzinfo=UTC)
    local_zone = ZoneInfo(zone)
    local = parsed.replace(tzinfo=local_zone)
    # A time inside a spring-forward gap converts to an instant whose local reading is a different time.
    if local.astimezone(UTC).astimezone(local_zone).replace(tzinfo=None) != parsed:
        raise ValueError(
            f"that local time does not exist in {zone} (clocks skip it at a daylight-saving change); "
            "choose a different time"
        )
    return local


def zone_fields(zone: str | None, next_run_at: datetime | None) -> dict[str, str]:
    """``timezone`` (the zone in use) and ``next_run_local`` (the next run there, with its UTC offset) for a result."""
    name = zone or request_timezone() or "UTC"
    fields = {"timezone": name}
    if next_run_at is not None:
        aware = next_run_at if next_run_at.tzinfo else next_run_at.replace(tzinfo=UTC)
        fields["next_run_local"] = aware.astimezone(ZoneInfo(name)).isoformat(timespec="seconds")
    return fields
