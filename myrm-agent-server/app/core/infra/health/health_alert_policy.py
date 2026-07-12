"""[INPUT]
- myrm_agent_harness.observability.diagnostics.protocols::HealthReport, redact_health_report (POS: health report model)
- app.core.infra.health.health_presenter::present_health_report (POS: deployment-aware presentation)
- app.services.event.app_event_bus::get_event_bus, AppEvent, AppEventType (POS: SSE fan-out)

[OUTPUT]
- should_publish_health_alert: policy gate for HEALTH_ALERT SSE
- publish_health_alerts: deduped fail-only publisher for critical components

[POS]
Server-layer alert policy SSOT. SystemResources never pushes; critical fails deduped 300s.
"""

from __future__ import annotations

import logging
import time

from myrm_agent_harness.observability.diagnostics.protocols import HealthReport, redact_health_report

from app.core.infra.health.health_presenter import present_health_report
from app.services.event.app_event_bus import AppEvent, AppEventType, get_event_bus

logger = logging.getLogger(__name__)

_PUSH_ON_FAIL: frozenset[str] = frozenset(
    {
        "AgentEngine",
        "Database",
        "Network",
        "VectorDB",
        "DLQ",
    }
)
_NEVER_PUSH: frozenset[str] = frozenset({"SystemResources"})
_DEDUP_SECONDS = 300.0

_last_published_at: dict[str, float] = {}


def reset_health_alert_dedup_for_tests() -> None:
    """Clear in-memory dedup state (tests only)."""
    _last_published_at.clear()


def should_publish_health_alert(component_name: str, status: str) -> bool:
    """Return True when a report should fan out as HEALTH_ALERT."""
    if component_name in _NEVER_PUSH:
        return False
    if status != "fail":
        return False
    return component_name in _PUSH_ON_FAIL


def _dedup_key(component_name: str, status: str, layer: str) -> str:
    return f"{layer}:{component_name}:{status}"


def _is_deduped(component_name: str, status: str, layer: str) -> bool:
    key = _dedup_key(component_name, status, layer)
    now = time.monotonic()
    last = _last_published_at.get(key)
    if last is not None and (now - last) < _DEDUP_SECONDS:
        return True
    _last_published_at[key] = now
    return False


def publish_health_alerts(reports: tuple[HealthReport, ...], *, layer: str) -> None:
    """Publish HEALTH_ALERT events for policy-approved fail reports (deduped)."""
    bus = get_event_bus()
    for report in reports:
        if not should_publish_health_alert(report.component_name, report.status):
            continue
        if _is_deduped(report.component_name, report.status, layer):
            logger.debug(
                "Suppressed duplicate health alert for %s (%s)",
                report.component_name,
                layer,
            )
            continue
        presented = present_health_report(report)
        redacted = redact_health_report(presented)
        bus.publish(
            AppEvent(
                event_type=AppEventType.HEALTH_ALERT,
                data={
                    "component": redacted.component_name,
                    "status": redacted.status,
                    "code": redacted.code,
                    "message": redacted.message,
                    "detail": redacted.detail,
                    "fix_suggestion": redacted.fix_suggestion,
                    "layer": layer,
                },
            )
        )
