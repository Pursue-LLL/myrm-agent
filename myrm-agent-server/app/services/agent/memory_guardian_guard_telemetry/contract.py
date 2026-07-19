"""@input: settings.control_plane + settings.memory_guardian_guard_telemetry
@output: guardian guard telemetry config/event dataclasses + label normalization helpers
@pos: Shared contract utilities for server-side guardian guard-unavailable telemetry dispatch.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from app.config.settings import settings

logger = logging.getLogger(__name__)

_DEFAULT_BATCH_SIZE: int = 24
_DEFAULT_FLUSH_INTERVAL_SECONDS: float = 3.0
_DEFAULT_QUEUE_SIZE: int = 256
_PENDING_STATE_FILENAME: str = "memory_guardian_guard_pending_envelopes.json"
_LABEL_UNKNOWN: str = "unknown"
_LABEL_MAX_LENGTH: int = 64
_ALLOWED_REASONS: frozenset[str] = frozenset(
    {
        "active_session_guard_unavailable",
        "budget_guard_unavailable",
        "capacity_guard_unavailable",
    }
)
_ALLOWED_GUARDS: frozenset[str] = frozenset(
    {
        "active_session",
        "budget",
        "capacity",
    }
)
_ALLOWED_FREQUENCY_TIERS: frozenset[str] = frozenset(
    {
        "conservative",
        "balanced",
        "aggressive",
    }
)


def normalize_governed_label(
    raw: str,
    *,
    allowed: frozenset[str],
) -> str:
    value = raw.strip().lower()
    if not value:
        return _LABEL_UNKNOWN
    if len(value) > _LABEL_MAX_LENGTH:
        return _LABEL_UNKNOWN
    if value not in allowed:
        return _LABEL_UNKNOWN
    return value


@dataclass(frozen=True)
class MemoryGuardianGuardTelemetryEvent:
    """Compact guard-unavailable labels used for aggregation and transport."""

    reason: str
    guard: str
    frequency_tier: str
    quiet_window_enabled: bool


@dataclass(frozen=True)
class MemoryGuardianGuardTelemetryConfig:
    """Validated runtime config for guardian guard telemetry dispatch."""

    control_plane_url: str
    telemetry_token: str
    telemetry_subject: str
    batch_size: int
    flush_interval_seconds: float
    queue_size: int
    pending_state_path: str = ""

    @classmethod
    def from_settings(cls) -> MemoryGuardianGuardTelemetryConfig | None:
        cp = settings.control_plane
        telemetry = settings.memory_guardian_guard_telemetry
        control_plane_url = cp.url.strip()
        telemetry_token = cp.telemetry_token.get_secret_value()
        telemetry_subject = cp.telemetry_subject.strip()

        present_count = sum(bool(value) for value in (control_plane_url, telemetry_token, telemetry_subject))
        if present_count == 0:
            logger.info("Guardian guard telemetry disabled: no control plane telemetry configured")
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
                "Guardian guard telemetry disabled: missing required settings: %s",
                ", ".join(missing),
            )
            return None

        batch_size = telemetry.batch_size if telemetry.batch_size > 0 else _DEFAULT_BATCH_SIZE
        flush_interval = (
            telemetry.flush_interval_seconds if telemetry.flush_interval_seconds > 0 else _DEFAULT_FLUSH_INTERVAL_SECONDS
        )
        queue_size = telemetry.queue_size if telemetry.queue_size > 0 else _DEFAULT_QUEUE_SIZE
        pending_state_path = str(
            Path(settings.database.state_dir).expanduser().resolve() / _PENDING_STATE_FILENAME
        )

        return cls(
            control_plane_url=control_plane_url.rstrip("/"),
            telemetry_token=telemetry_token,
            telemetry_subject=telemetry_subject,
            batch_size=batch_size,
            flush_interval_seconds=flush_interval,
            queue_size=queue_size,
            pending_state_path=pending_state_path,
        )


__all__ = [
    "MemoryGuardianGuardTelemetryConfig",
    "MemoryGuardianGuardTelemetryEvent",
    "_ALLOWED_FREQUENCY_TIERS",
    "_ALLOWED_GUARDS",
    "_ALLOWED_REASONS",
    "normalize_governed_label",
]
