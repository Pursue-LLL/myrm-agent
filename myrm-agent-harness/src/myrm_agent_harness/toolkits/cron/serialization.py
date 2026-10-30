"""JSON-safe conversion of cron value objects, for the columns and payloads that persist them.

[INPUT]
- toolkits.cron.types::ActiveHours, DeliveryConfig, FailureAlertConfig, Schedule, ScheduleKind (POS: Cron job domain types.)

[OUTPUT]
- dict_to_active_hours / active_hours_to_dict: ``ActiveHours`` <-> JSON dict
- dict_to_delivery / delivery_to_dict: ``DeliveryConfig`` <-> JSON dict
- dict_to_failure_alert / failure_alert_to_dict: ``FailureAlertConfig`` (or ``False`` = disabled) <-> JSON value
- dict_to_schedule / schedule_to_dict: ``Schedule`` <-> JSON dict

[POS]
Storage-edge converters between the frozen cron value objects and their persisted JSON form.
Kept apart from ``types`` so that module stays pure data definitions.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal, cast

from myrm_agent_harness.toolkits.cron.types import (
    ActiveHours,
    DeliveryConfig,
    FailureAlertConfig,
    Schedule,
    ScheduleKind,
)


def dict_to_active_hours(d: dict[str, str] | None) -> ActiveHours | None:
    """Convert a JSON dict to ``ActiveHours``, or None if missing/empty."""
    if not d:
        return None
    start = d.get("start", "")
    end = d.get("end", "")
    if not start or not end:
        return None
    return ActiveHours(start=start, end=end, tz=d.get("tz", "UTC"))


def active_hours_to_dict(ah: ActiveHours | None) -> dict[str, str] | None:
    """Serialise ``ActiveHours`` to a JSON-safe dict."""
    if ah is None:
        return None
    return {"start": ah.start, "end": ah.end, "tz": ah.tz}


def dict_to_delivery(d: dict[str, str | None] | None) -> DeliveryConfig | None:
    """Convert a JSON dict to ``DeliveryConfig``, or None if missing/empty."""
    if not d:
        return None
    return DeliveryConfig(
        channel=str(d.get("channel", "chat")),
        target=d.get("target"),
        secret=d.get("secret"),
        thread_id=d.get("thread_id"),
    )


def delivery_to_dict(dc: DeliveryConfig | None) -> dict[str, str | None] | None:
    """Serialise ``DeliveryConfig`` to a JSON-safe dict, or None."""
    if dc is None:
        return None
    d: dict[str, str | None] = {"channel": dc.channel, "target": dc.target}
    if dc.secret:
        d["secret"] = dc.secret
    if dc.thread_id:
        d["thread_id"] = dc.thread_id
    return d


def dict_to_failure_alert(
    d: dict[str, object] | bool | None,
) -> FailureAlertConfig | Literal[False] | None:
    """Convert a JSON value to ``FailureAlertConfig``, ``False``, or ``None``."""
    if d is None:
        return None
    if d is False:
        return False
    if not isinstance(d, dict):
        return None
    return FailureAlertConfig(
        enabled=bool(d.get("enabled", True)),
        after=int(cast("int | str", d.get("after", 3))),
        cooldown_seconds=int(cast("int | str", d.get("cooldown_seconds", 300))),
        delivery=dict_to_delivery(d.get("delivery")),  # type: ignore[arg-type]
    )


def failure_alert_to_dict(
    fa: FailureAlertConfig | Literal[False] | None,
) -> dict[str, object] | Literal[False] | None:
    """Serialise ``FailureAlertConfig`` to a JSON-safe value."""
    if fa is None:
        return None
    if fa is False:
        return False
    d: dict[str, object] = {
        "enabled": fa.enabled,
        "after": fa.after,
        "cooldown_seconds": fa.cooldown_seconds,
    }
    if fa.delivery:
        d["delivery"] = delivery_to_dict(fa.delivery)
    return d


def dict_to_schedule(d: dict[str, str | int | None]) -> Schedule:
    """Convert a JSON-serialised schedule dict to a ``Schedule`` domain object."""
    run_at = None
    raw_run_at = d.get("run_at")
    if raw_run_at and isinstance(raw_run_at, str):
        run_at = datetime.fromisoformat(raw_run_at)
        if run_at.tzinfo is None:
            run_at = run_at.replace(tzinfo=UTC)

    raw_stagger = d.get("stagger_ms")
    stagger_ms = int(raw_stagger) if raw_stagger is not None else None
    raw_interval = d.get("interval_ms")

    return Schedule(
        kind=ScheduleKind(str(d["kind"])),
        expr=str(d["expr"]) if d.get("expr") else None,
        tz=str(d["tz"]) if d.get("tz") else None,
        interval_ms=int(raw_interval) if raw_interval else None,
        run_at=run_at,
        stagger_ms=stagger_ms,
    )


def schedule_to_dict(s: Schedule) -> dict[str, str | int]:
    """Serialise a ``Schedule`` to a JSON-safe dict."""
    d: dict[str, str | int] = {"kind": s.kind}
    if s.expr:
        d["expr"] = s.expr
    if s.tz:
        d["tz"] = s.tz
    if s.interval_ms:
        d["interval_ms"] = s.interval_ms
    if s.run_at:
        d["run_at"] = s.run_at.isoformat()
    if s.stagger_ms is not None:
        d["stagger_ms"] = s.stagger_ms
    return d
