"""Auth audit logger — JSONL structured logging for authentication events.

Records auth success/failure events for security analysis and incident response.
Only active in WebUI Remote and Sandbox modes (no value for local loopback).

[INPUT]
- myrm_agent_harness.utils.log_rotation::FileLogRotator (POS: File log rotation utility)
- app.config.settings::get_settings (POS: Application settings)

[OUTPUT]
- log_auth_event(): append auth event to JSONL audit file (auto-rotation)
- AuthEventType: enum of auth event types
- AUDIT_LOG_FILE: path to the audit JSONL file

[POS]
Auth audit JSONL logger. Appends structured auth events to a rotated JSONL file.
"""

from __future__ import annotations

import json
import logging
import time
from enum import Enum
from pathlib import Path

from myrm_agent_harness.utils.log_rotation import FileLogRotator, LogRotationConfig

logger = logging.getLogger(__name__)

AUDIT_LOG_FILE = Path(".myrm/logs/auth_audit.jsonl")

_rotator: FileLogRotator | None = None


def _get_rotator() -> FileLogRotator:
    """Get or create log rotator (lazy init)."""
    global _rotator
    if _rotator is None:
        from app.config.settings import get_settings

        settings = get_settings()
        config = LogRotationConfig(
            max_size_mb=settings.auth_audit_log_max_size_mb,
            max_age_days=settings.auth_audit_log_max_age_days,
            retention_days=settings.auth_audit_log_retention_days,
            compress=settings.auth_audit_log_compress,
        )
        _rotator = FileLogRotator(config)
    return _rotator


class AuthEventType(str, Enum):
    """Auth event types aligned with single-tenant SANDBOX_API_KEY model."""

    AUTH_SUCCESS = "auth_success"
    AUTH_FAILURE = "auth_failure"
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"


def log_auth_event(
    event_type: AuthEventType,
    client_ip: str,
    *,
    auth_source: str | None = None,
    metadata: dict[str, object] | None = None,
) -> None:
    """Append an auth event to the JSONL audit file.

    Args:
        event_type: Event classification.
        client_ip: Originating IP address.
        auth_source: How the request was authenticated (e.g. "sandbox_api_key").
        metadata: Optional extra context.
    """
    AUDIT_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

    rotator = _get_rotator()
    if rotator.should_rotate(AUDIT_LOG_FILE):
        rotator.rotate(AUDIT_LOG_FILE)

    event: dict[str, object] = {
        "ts": round(time.time(), 3),
        "type": event_type.value,
        "ip": client_ip,
    }
    if auth_source:
        event["source"] = auth_source
    if metadata:
        event["meta"] = metadata

    try:
        with AUDIT_LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.error("Failed to write auth audit log: %s", e, exc_info=True)


__all__ = ["log_auth_event", "AuthEventType", "AUDIT_LOG_FILE"]
