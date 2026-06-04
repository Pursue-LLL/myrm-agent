"""Read auth audit events from JSONL on disk."""

from __future__ import annotations

import json

from app.middleware.auth_audit import AUDIT_LOG_FILE


def read_auth_audit_events(
    *,
    start_time: float | None = None,
    end_time: float | None = None,
) -> list[dict[str, object]]:
    """Read and filter events from JSONL audit log (per-line fault tolerant)."""
    if not AUDIT_LOG_FILE.exists():
        return []

    events: list[dict[str, object]] = []
    with AUDIT_LOG_FILE.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(parsed, dict):
                continue
            event: dict[str, object] = {str(key): value for key, value in parsed.items()}
            ts_raw = event.get("ts", 0)
            ts = float(ts_raw) if isinstance(ts_raw, (int, float)) else 0.0
            if start_time is not None and ts < start_time:
                continue
            if end_time is not None and ts > end_time:
                continue
            events.append(event)
    return events
