"""Parameter parsing for the ``cron_manage`` tool.

Turns the tool's flat string / int parameters into typed cron values (schedule, expiry,
active hours, monitor config, trigger config, session target, ID lists). Every parser
returns an error message instead of raising, so the tool can hand the text straight back
to the model.

[INPUT]
- infra.incremental.types::MonitorConfig, MonitorType (POS: 增量监控领域类型)
- toolkits.cron.triggers::PollTrigger, StreamProtocol, StreamTrigger, TriggerConfig (POS: 触发器类型定义与安全辅助)
- toolkits.cron.types::ActiveHours, Schedule, ScheduleKind, SessionTarget (POS: cron 数据模型)

[OUTPUT]
- _build_schedule / _parse_expires_after / _build_active_hours / _build_monitor_config /
  _parse_csv_tuple / _parse_context_from / _parse_session_mode / _build_trigger_config:
  tool parameter -> typed value, or an error message for the model
- _MIN_INTERVAL_MINUTES / _MIN_INTERVAL_MS: the shortest recurring interval the tool accepts

[POS]
Parameter-parsing half of the ``cron_manage`` tool. Kept apart from the action
implementations so the rules that reject a parameter can be read and tested without a
``CronManager``.
"""

from __future__ import annotations

import json
from datetime import UTC, timedelta
from datetime import datetime as dt
from typing import get_args

from myrm_agent_harness.infra.incremental.types import MonitorConfig, MonitorType
from myrm_agent_harness.toolkits.cron.triggers import (
    PollTrigger,
    StreamProtocol,
    StreamTrigger,
    TriggerConfig,
)
from myrm_agent_harness.toolkits.cron.types import (
    ActiveHours,
    Schedule,
    ScheduleKind,
    SessionTarget,
)

_MIN_INTERVAL_MINUTES = 5
_MIN_INTERVAL_MS = _MIN_INTERVAL_MINUTES * 60_000


# ---------------------------------------------------------------------------
# Schedule builder (implicit type detection)
# ---------------------------------------------------------------------------


def _build_schedule(
    cron_expr: str,
    every_minutes: int,
    at: str,
    tz: str,
) -> tuple[str | None, Schedule | None]:
    """Return (error_msg, Schedule) — exactly one will be non-None."""
    filled = sum([bool(cron_expr), every_minutes > 0, bool(at)])
    if filled == 0:
        return "Provide one of: cron_expr, every_minutes, or at.", None
    if filled > 1:
        return "Provide only ONE schedule param (cron_expr / every_minutes / at).", None

    if cron_expr:
        return None, Schedule(kind=ScheduleKind.CRON, expr=cron_expr, tz=tz or None)
    if every_minutes > 0:
        if every_minutes < _MIN_INTERVAL_MINUTES:
            return (
                f"every_minutes must be >= {_MIN_INTERVAL_MINUTES}. For one-time tasks use 'at' instead.",
                None,
            )
        return None, Schedule(kind=ScheduleKind.INTERVAL, interval_ms=every_minutes * 60_000)
    if at:
        run_at = dt.fromisoformat(at)
        if run_at.tzinfo is None:
            run_at = run_at.replace(tzinfo=UTC)
        return None, Schedule(kind=ScheduleKind.ONCE, run_at=run_at)

    return "Could not determine schedule type.", None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DURATION_UNITS: dict[str, int] = {"d": 1, "w": 7, "m": 30}


def _parse_expires_after(value: str) -> dt | None:
    """Parse a human-friendly duration ("3d", "2w", "3m") or ISO 8601 datetime."""
    value = value.strip()
    if not value:
        return None
    if len(value) >= 2 and value[-1] in _DURATION_UNITS and value[:-1].isdigit():
        days = int(value[:-1]) * _DURATION_UNITS[value[-1]]
        return dt.now(UTC) + timedelta(days=days)
    parsed = dt.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def _build_active_hours(start: str, end: str, active_tz: str) -> ActiveHours | None:
    """Build ActiveHours if both start and end are provided."""
    if not start.strip() or not end.strip():
        return None
    return ActiveHours(start=start.strip(), end=end.strip(), tz=active_tz.strip() or "UTC")


_MIN_POLL_INTERVAL_SECONDS = 60
_VALID_STREAM_PROTOCOLS = {"ws", "sse"}
_MONITOR_TYPES: dict[str, MonitorType] = {kind: kind for kind in get_args(MonitorType)}


def _build_monitor_config(
    monitor_type: str,
    monitor_enabled: bool,
) -> tuple[str | None, MonitorConfig | None, bool]:
    """Build MonitorConfig from tool parameters.

    Returns (error_msg, config, should_clear).  When ``monitor_type`` is
    ``"off"``, ``should_clear=True`` signals that monitoring should be removed.
    """
    mt = monitor_type.strip().lower()
    if mt == "off":
        return None, None, True
    if not monitor_enabled and not mt:
        return None, None, False
    if not monitor_enabled:
        return "Set monitor_enabled=true to enable monitoring.", None, False
    mt = mt or "set"
    if (monitor_kind := _MONITOR_TYPES.get(mt)) is None:
        valid = ", ".join(sorted(_MONITOR_TYPES))
        return f"Invalid monitor_type '{monitor_type}'. Must be one of: {valid}.", None, False
    return None, MonitorConfig(monitor_type=monitor_kind, enabled=True), False


def _parse_csv_tuple(raw: str) -> tuple[str, ...]:
    """Parse comma-separated IDs into a deduplicated tuple."""
    if not raw.strip():
        return ()
    seen: set[str] = set()
    items: list[str] = []
    for part in raw.split(","):
        token = part.strip()
        if not token or token in seen:
            continue
        seen.add(token)
        items.append(token)
    return tuple(items)


def _parse_context_from(raw: str) -> tuple[str, ...]:
    """Parse comma-separated job IDs into a deduplicated tuple."""
    if not raw.strip():
        return ()
    ids = [s.strip() for s in raw.split(",") if s.strip()]
    seen: set[str] = set()
    unique: list[str] = []
    for ref_id in ids:
        if ref_id not in seen:
            seen.add(ref_id)
            unique.append(ref_id)
    return tuple(unique)


_SESSION_MODE_MAP: dict[str, SessionTarget] = {
    "isolated": SessionTarget.ISOLATED,
    "main": SessionTarget.MAIN,
    "daily": SessionTarget.DAILY,
}


def _parse_session_mode(raw: str, default: SessionTarget = SessionTarget.ISOLATED) -> tuple[str | None, SessionTarget]:
    """Parse session_mode string into SessionTarget enum; a blank value yields ``default``.

    Returns (error_msg, SessionTarget). error_msg is None on success.
    """
    cleaned = raw.strip().lower()
    if not cleaned:
        return None, default
    target = _SESSION_MODE_MAP.get(cleaned)
    if target is None:
        valid = ", ".join(sorted(_SESSION_MODE_MAP))
        return f"Invalid session_mode '{raw}'. Must be one of: {valid}.", default
    return None, target


def _build_trigger_config(
    stream_url: str,
    stream_protocol: str,
    stream_filter_json_path: str,
    stream_filter_regex: str,
    stream_headers: str,
    poll_url: str,
    poll_json_path: str,
    poll_interval_seconds: int,
) -> tuple[str | None, TriggerConfig | None]:
    """Build TriggerConfig from stream/poll tool parameters.

    Returns (error_msg, TriggerConfig).  Both None when neither is specified.
    """
    streams: tuple[StreamTrigger, ...] = ()
    polls: tuple[PollTrigger, ...] = ()

    if stream_url.strip():
        proto_str = stream_protocol.strip().lower() or "ws"
        if proto_str not in _VALID_STREAM_PROTOCOLS:
            valid = ", ".join(sorted(_VALID_STREAM_PROTOCOLS))
            return f"Invalid stream_protocol '{stream_protocol}'. Must be one of: {valid}.", None

        headers: dict[str, str] = {}
        if stream_headers.strip():
            try:
                headers = json.loads(stream_headers)
            except (json.JSONDecodeError, TypeError):
                return "Error: stream_headers must be valid JSON object.", None

        streams = (
            StreamTrigger(
                url=stream_url.strip(),
                protocol=StreamProtocol(proto_str),
                filter_json_path=stream_filter_json_path.strip() or None,
                filter_regex=stream_filter_regex.strip() or None,
                headers=headers,
            ),
        )

    if poll_url.strip():
        interval = poll_interval_seconds if poll_interval_seconds > 0 else 300
        if interval < _MIN_POLL_INTERVAL_SECONDS:
            return (
                f"poll_interval_seconds must be >= {_MIN_POLL_INTERVAL_SECONDS}.",
                None,
            )
        polls = (
            PollTrigger(
                url=poll_url.strip(),
                json_path=poll_json_path.strip() or None,
                interval_seconds=interval,
            ),
        )

    if not streams and not polls:
        return None, None

    return None, TriggerConfig(streams=streams, polls=polls)
