"""@input: settings.control_plane + settings.memory_brief_status_telemetry + normalized payload mappings
@output: memory brief telemetry config/event dataclasses + phase parsing + payload normalization helpers
@pos: Shared contract and normalization utilities for server-side memory brief telemetry dispatch.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from app.config.settings import settings

logger = logging.getLogger(__name__)

_DEFAULT_BATCH_SIZE: int = 32
_DEFAULT_FLUSH_INTERVAL_SECONDS: float = 3.0
_DEFAULT_QUEUE_SIZE: int = 512
_LABEL_NONE: str = "none"
_PHASE_STREAM: str = "stream"
_PHASE_PERSIST: str = "persist"
_DEFAULT_VALID_PHASES: frozenset[str] = frozenset({_PHASE_STREAM, _PHASE_PERSIST})
_DROPPED_STATE_FILENAME: str = "memory_brief_status_dropped_aggregates.json"


@dataclass(frozen=True)
class MemoryBriefStatusTelemetryEvent:
    """Compact per-turn labels used for aggregation and transport."""

    phase: str
    brief_state: str
    brief_reason: str
    brief_source: str
    injection_state: str
    injection_source: str
    injection_reason: str


@dataclass(frozen=True)
class MemoryBriefStatusTelemetryConfig:
    """Validated runtime config for memory brief status telemetry dispatch."""

    control_plane_url: str
    telemetry_token: str
    telemetry_subject: str
    batch_size: int
    flush_interval_seconds: float
    queue_size: int
    allowed_phases: frozenset[str]
    dropped_state_path: str = ""

    @classmethod
    def from_settings(cls) -> MemoryBriefStatusTelemetryConfig | None:
        cp = settings.control_plane
        telemetry = settings.memory_brief_status_telemetry
        control_plane_url = cp.url.strip()
        telemetry_token = cp.telemetry_token.get_secret_value()
        telemetry_subject = cp.telemetry_subject.strip()

        present_count = sum(bool(value) for value in (control_plane_url, telemetry_token, telemetry_subject))
        if present_count == 0:
            logger.info("Memory brief status telemetry disabled: no control plane telemetry configured")
            return None

        missing = [
            label
            for label, value in (
                ("CONTROL_PLANE_URL", control_plane_url),
                ("CONTROL_PLANE_TELEMETRY_TOKEN", telemetry_token),
                ("CONTROL_PLANE_TELEMETRY_SUBJECT", telemetry_subject),
            )
            if not value
        ]
        if missing:
            logger.warning(
                "Memory brief status telemetry disabled: missing required settings: %s",
                ", ".join(missing),
            )
            return None

        batch_size = telemetry.batch_size if telemetry.batch_size > 0 else _DEFAULT_BATCH_SIZE
        flush_interval = (
            telemetry.flush_interval_seconds if telemetry.flush_interval_seconds > 0 else _DEFAULT_FLUSH_INTERVAL_SECONDS
        )
        queue_size = telemetry.queue_size if telemetry.queue_size > 0 else _DEFAULT_QUEUE_SIZE
        allowed_phases = parse_allowed_phases_config(telemetry.allowed_phases)
        dropped_state_path = str(
            Path(settings.database.state_dir).expanduser().resolve() / _DROPPED_STATE_FILENAME
        )

        return cls(
            control_plane_url=control_plane_url.rstrip("/"),
            telemetry_token=telemetry_token,
            telemetry_subject=telemetry_subject,
            batch_size=batch_size,
            flush_interval_seconds=flush_interval,
            queue_size=queue_size,
            allowed_phases=allowed_phases,
            dropped_state_path=dropped_state_path,
        )


def normalize_label(raw: object) -> str:
    if not isinstance(raw, str):
        return _LABEL_NONE
    value = raw.strip()
    return value or _LABEL_NONE


def parse_allowed_phases_config(raw: str) -> frozenset[str]:
    values = {
        normalize_label(part)
        for part in raw.split(",")
    }
    requested = {phase for phase in values if phase != _LABEL_NONE}
    if not requested:
        logger.warning(
            "Memory brief status telemetry allowed phases is empty; falling back to default phases=%s",
            ",".join(sorted(_DEFAULT_VALID_PHASES)),
        )
        return _DEFAULT_VALID_PHASES

    unsupported = sorted(requested - _DEFAULT_VALID_PHASES)
    if unsupported:
        logger.warning(
            "Memory brief status telemetry allowed phases contains unsupported values=%s; only %s are accepted",
            ",".join(unsupported),
            ",".join(sorted(_DEFAULT_VALID_PHASES)),
        )

    supported = requested & _DEFAULT_VALID_PHASES
    if not supported:
        logger.warning(
            "Memory brief status telemetry allowed phases contains no supported values; falling back to default phases=%s",
            ",".join(sorted(_DEFAULT_VALID_PHASES)),
        )
        return _DEFAULT_VALID_PHASES
    return frozenset(supported)


def build_memory_brief_status_event(
    phase: str,
    payload: object,
    *,
    allowed_phases: frozenset[str] = _DEFAULT_VALID_PHASES,
) -> MemoryBriefStatusTelemetryEvent | None:
    if not isinstance(payload, Mapping):
        return None
    normalized_phase = normalize_label(phase)
    if normalized_phase == _LABEL_NONE:
        return None
    if normalized_phase not in allowed_phases:
        logger.warning("Skipping memory brief status telemetry event for unsupported phase=%s", normalized_phase)
        return None
    brief_state = normalize_label(payload.get("state"))
    if brief_state == _LABEL_NONE:
        return None

    injection = payload.get("injection")
    injection_mapping = injection if isinstance(injection, Mapping) else {}
    return MemoryBriefStatusTelemetryEvent(
        phase=normalized_phase,
        brief_state=brief_state,
        brief_reason=normalize_label(payload.get("reason")),
        brief_source=normalize_label(payload.get("source")),
        injection_state=normalize_label(injection_mapping.get("state")),
        injection_source=normalize_label(injection_mapping.get("source")),
        injection_reason=normalize_label(injection_mapping.get("reason")),
    )


__all__ = [
    "MemoryBriefStatusTelemetryConfig",
    "MemoryBriefStatusTelemetryEvent",
    "_PHASE_PERSIST",
    "_PHASE_STREAM",
    "build_memory_brief_status_event",
]
