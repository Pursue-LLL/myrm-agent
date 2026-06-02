"""Auth audit log REST API — query, stats, and export for auth events.

[INPUT]
- app.middleware.auth_audit::AUDIT_LOG_FILE (POS: Auth audit JSONL logger)
- app.middleware.auth_audit::AuthEventType (POS: Auth audit JSONL logger)

[OUTPUT]
- router: FastAPI APIRouter with 3 endpoints
  - GET /audit/auth/logs — query with filters (time range, event type, IP)
  - GET /audit/auth/stats — aggregated statistics
  - GET /audit/auth/export — CSV/JSON file export

[POS]
Auth audit query API. JSONL parsing is per-line fault-tolerant.
"""

from __future__ import annotations

import csv
import io
import json
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import BaseModel, Field

from app.middleware.auth_audit import AUDIT_LOG_FILE, AuthEventType

router = APIRouter(prefix="/audit/auth", tags=["audit"])


class AuthAuditLog(BaseModel):
    """Single auth audit log record."""

    timestamp: float = Field(description="UTC Unix timestamp")
    event_type: str = Field(description="Event type (auth_success / auth_failure / rate_limit_exceeded)")
    client_ip: str = Field(description="Client IP address")
    auth_source: str | None = Field(default=None, description="Auth method (e.g. sandbox_api_key)")
    metadata: dict[str, object] | None = Field(default=None, description="Extra context")


class AuthAuditStats(BaseModel):
    """Aggregated auth audit statistics."""

    total_events: int
    auth_success_count: int
    auth_failure_count: int
    rate_limit_count: int
    unique_ips: int
    top_failure_ips: list[tuple[str, int]] = Field(description="Top 10 IPs by failure count")


def _read_events(
    *,
    start_time: float | None = None,
    end_time: float | None = None,
) -> list[dict[str, object]]:
    """Read and filter events from JSONL audit log."""
    if not AUDIT_LOG_FILE.exists():
        return []

    events: list[dict[str, object]] = []
    with AUDIT_LOG_FILE.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(parsed, dict):
                continue
            event: dict[str, object] = {str(k): v for k, v in parsed.items()}
            ts_raw = event.get("ts", 0)
            ts = float(ts_raw) if isinstance(ts_raw, (int, float)) else 0.0
            if start_time is not None and ts < start_time:
                continue
            if end_time is not None and ts > end_time:
                continue
            events.append(event)
    return events


@router.get("/logs", response_model=list[AuthAuditLog])
async def get_auth_audit_logs(
    start_time: float | None = Query(None, description="Start time (UTC timestamp)"),
    end_time: float | None = Query(None, description="End time (UTC timestamp)"),
    event_type: str | None = Query(None, description="Filter by event type"),
    client_ip: str | None = Query(None, description="Filter by client IP"),
    limit: int = Query(100, ge=1, le=1000, description="Max results"),
) -> list[AuthAuditLog]:
    """Query auth audit logs with optional filters. Returns most recent first."""
    try:
        events = _read_events(start_time=start_time, end_time=end_time)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read audit logs: {e}") from e

    logs: list[AuthAuditLog] = []
    for event in events:
        if event_type and event.get("type") != event_type:
            continue
        if client_ip and event.get("ip") != client_ip:
            continue

        ts_raw = event.get("ts", 0)
        ts = float(ts_raw) if isinstance(ts_raw, (int, float)) else 0.0
        type_raw = event.get("type")
        event_type_str = type_raw if isinstance(type_raw, str) else str(type_raw)
        ip_raw = event.get("ip", "unknown")
        record_client_ip = ip_raw if isinstance(ip_raw, str) else str(ip_raw)
        src_raw = event.get("source")
        auth_source = src_raw if isinstance(src_raw, str) else (str(src_raw) if src_raw is not None else None)
        meta_raw = event.get("meta")
        metadata: dict[str, object] | None
        if meta_raw is None:
            metadata = None
        elif isinstance(meta_raw, dict):
            metadata = {str(k): v for k, v in meta_raw.items()}
        else:
            metadata = None

        logs.append(
            AuthAuditLog(
                timestamp=ts,
                event_type=event_type_str,
                client_ip=record_client_ip,
                auth_source=auth_source,
                metadata=metadata,
            )
        )
        if len(logs) >= limit:
            break

    logs.reverse()
    return logs


@router.get("/stats", response_model=AuthAuditStats)
async def get_auth_audit_stats(
    start_time: float | None = Query(None, description="Start time (UTC timestamp)"),
    end_time: float | None = Query(None, description="End time (UTC timestamp)"),
) -> AuthAuditStats:
    """Get aggregated auth audit statistics."""
    try:
        events = _read_events(start_time=start_time, end_time=end_time)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read audit logs: {e}") from e

    success_val = AuthEventType.AUTH_SUCCESS.value
    failure_val = AuthEventType.AUTH_FAILURE.value
    rate_limit_val = AuthEventType.RATE_LIMIT_EXCEEDED.value

    auth_success = sum(1 for evt in events if evt.get("type") == success_val)
    auth_failure = sum(1 for evt in events if evt.get("type") == failure_val)
    rate_limit = sum(1 for evt in events if evt.get("type") == rate_limit_val)

    unique_ips = len({evt.get("ip", "unknown") for evt in events})

    ip_failures: dict[str, int] = {}
    for evt in events:
        if evt.get("type") == failure_val:
            ip = str(evt.get("ip", "unknown"))
            ip_failures[ip] = ip_failures.get(ip, 0) + 1

    top_failure_ips = sorted(ip_failures.items(), key=lambda x: x[1], reverse=True)[:10]

    return AuthAuditStats(
        total_events=len(events),
        auth_success_count=auth_success,
        auth_failure_count=auth_failure,
        rate_limit_count=rate_limit,
        unique_ips=unique_ips,
        top_failure_ips=top_failure_ips,
    )


@router.get("/export", response_class=Response)
async def export_auth_audit_logs(
    start_time: float | None = Query(None, description="Start time (UTC timestamp)"),
    end_time: float | None = Query(None, description="End time (UTC timestamp)"),
    format: Literal["csv", "json"] = Query("csv", description="Export format"),
) -> Response:
    """Export auth audit logs as CSV or JSON file."""
    try:
        events = _read_events(start_time=start_time, end_time=end_time)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to export audit logs: {e}") from e

    if not events:
        raise HTTPException(status_code=404, detail="No audit log entries found")

    if format == "json":
        return Response(
            content=json.dumps(events, ensure_ascii=False, indent=2),
            media_type="application/json",
            headers={"Content-Disposition": "attachment; filename=auth_audit.json"},
        )

    output = io.StringIO()
    fieldnames = ["timestamp", "event_type", "client_ip", "auth_source", "metadata"]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for event in events:
        writer.writerow(
            {
                "timestamp": event.get("ts"),
                "event_type": event.get("type"),
                "client_ip": event.get("ip"),
                "auth_source": event.get("source", ""),
                "metadata": json.dumps(event.get("meta", {})),
            }
        )

    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=auth_audit.csv"},
    )


__all__ = ["router"]
