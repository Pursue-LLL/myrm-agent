"""Platform audit logs for the security dashboard (sandbox CP or local auth).

[INPUT]
- app.services.audit.auth_log_reader::read_auth_audit_events (POS: 本地 auth JSONL 读取)
- app.services.security.cp_security_dashboard::get_cp_* (POS: 沙箱内 CP internal 调用)

[OUTPUT]
- fetch_platform_audit_logs / fetch_platform_audit_stats / export_platform_audit_logs

[POS]
安全仪表盘平台审计聚合。沙箱走 CP internal；本地走 auth JSONL。
"""

from __future__ import annotations

import csv
import io
import json
import logging
from datetime import UTC, datetime
from typing import Literal

import httpx
from fastapi import HTTPException
from fastapi.responses import Response

from app.api.security.dashboard_models import (
    PlatformAuditEvent,
    PlatformAuditEventCount,
    PlatformAuditLogsResponse,
    PlatformAuditStatsResponse,
    PlatformAuditSuccessFailed,
    PlatformAuditTimeSeriesPoint,
    PlatformAuditTopIp,
)
from app.config.deploy_mode import is_sandbox
from app.middleware.auth_audit import AuthEventType
from app.services.audit.auth_log_reader import read_auth_audit_events
from app.services.security.cp_security_dashboard import get_cp_api_base, get_cp_request_headers

logger = logging.getLogger(__name__)

_REQUEST_TIMEOUT = 8.0


def _auth_result(event_type: str) -> str:
    if event_type == AuthEventType.AUTH_SUCCESS.value:
        return "success"
    if event_type == AuthEventType.AUTH_FAILURE.value:
        return "failed"
    if event_type == AuthEventType.RATE_LIMIT_EXCEEDED.value:
        return "rate_limited"
    return "unknown"


def _auth_severity(event_type: str) -> str:
    if event_type in (AuthEventType.AUTH_FAILURE.value, AuthEventType.RATE_LIMIT_EXCEEDED.value):
        return "warn"
    return "info"


def _map_auth_events(events: list[dict[str, object]], *, limit: int) -> list[PlatformAuditEvent]:
    mapped: list[PlatformAuditEvent] = []
    for event in reversed(events):
        type_raw = event.get("type")
        event_type = type_raw if isinstance(type_raw, str) else str(type_raw)
        ts_raw = event.get("ts", 0)
        ts = float(ts_raw) if isinstance(ts_raw, (int, float)) else 0.0
        ip_raw = event.get("ip")
        ip_address = ip_raw if isinstance(ip_raw, str) else (str(ip_raw) if ip_raw is not None else None)
        meta_raw = event.get("meta")
        metadata: dict[str, object] = (
            {str(k): v for k, v in meta_raw.items()} if isinstance(meta_raw, dict) else {}
        )
        mapped.append(
            PlatformAuditEvent(
                event_type=event_type,
                timestamp=datetime.fromtimestamp(ts, tz=UTC).isoformat(),
                severity=_auth_severity(event_type),
                user_id=None,
                sandbox_id=None,
                resource=None,
                action="auth",
                result=_auth_result(event_type),
                metadata=metadata,
                ip_address=ip_address,
                trace_id=None,
                request_id=None,
                traffic_class=None,
                source="auth",
            )
        )
        if len(mapped) >= limit:
            break
    return mapped


def _build_auth_stats(events: list[dict[str, object]], *, hours: int) -> PlatformAuditStatsResponse:
    success_val = AuthEventType.AUTH_SUCCESS.value
    failure_val = AuthEventType.AUTH_FAILURE.value

    ip_counts: dict[str, int] = {}
    type_counts: dict[str, int] = {}
    success_count = 0
    failed_count = 0

    for event in events:
        type_raw = event.get("type")
        event_type = type_raw if isinstance(type_raw, str) else str(type_raw)
        type_counts[event_type] = type_counts.get(event_type, 0) + 1
        if event_type == success_val:
            success_count += 1
        elif event_type == failure_val:
            failed_count += 1
        ip_raw = event.get("ip")
        if isinstance(ip_raw, str) and ip_raw:
            ip_counts[ip_raw] = ip_counts.get(ip_raw, 0) + 1

    top_ips = [
        PlatformAuditTopIp(ip_address=ip, request_count=count)
        for ip, count in sorted(ip_counts.items(), key=lambda item: item[1], reverse=True)[:10]
    ]
    event_distribution = [
        PlatformAuditEventCount(event_type=event_type, count=count)
        for event_type, count in sorted(type_counts.items(), key=lambda item: item[1], reverse=True)
    ]

    return PlatformAuditStatsResponse(
        time_series=[],
        top_ips=top_ips,
        event_distribution=event_distribution,
        success_vs_failed=PlatformAuditSuccessFailed(success=success_count, failed=failed_count),
        total_events=len(events),
        time_range_hours=hours,
        is_live=True,
    )


def _map_cp_event(raw: dict[str, object]) -> PlatformAuditEvent:
    return PlatformAuditEvent(
        event_type=str(raw.get("event_type") or ""),
        timestamp=str(raw.get("timestamp") or ""),
        severity=str(raw.get("severity") or "info"),
        user_id=str(raw["user_id"]) if raw.get("user_id") is not None else None,
        sandbox_id=str(raw["sandbox_id"]) if raw.get("sandbox_id") is not None else None,
        resource=str(raw["resource"]) if raw.get("resource") is not None else None,
        action=str(raw.get("action") or ""),
        result=str(raw.get("result") or ""),
        metadata=(
            {str(k): v for k, v in raw["metadata"].items()}
            if isinstance(raw.get("metadata"), dict)
            else {}
        ),
        ip_address=str(raw["ip_address"]) if raw.get("ip_address") is not None else None,
        trace_id=str(raw["trace_id"]) if raw.get("trace_id") is not None else None,
        request_id=str(raw["request_id"]) if raw.get("request_id") is not None else None,
        traffic_class=str(raw["traffic_class"]) if raw.get("traffic_class") is not None else None,
        source="control_plane",
    )


def _map_cp_stats(raw: dict[str, object]) -> PlatformAuditStatsResponse:
    time_series_raw = raw.get("time_series")
    time_series: list[PlatformAuditTimeSeriesPoint] = []
    if isinstance(time_series_raw, list):
        for item in time_series_raw:
            if isinstance(item, dict):
                time_series.append(
                    PlatformAuditTimeSeriesPoint(
                        timestamp=str(item.get("timestamp") or ""),
                        total=int(item.get("total") or 0),
                        success=int(item.get("success") or 0),
                        failed=int(item.get("failed") or 0),
                    )
                )

    top_ips_raw = raw.get("top_ips")
    top_ips: list[PlatformAuditTopIp] = []
    if isinstance(top_ips_raw, list):
        for item in top_ips_raw:
            if isinstance(item, dict):
                top_ips.append(
                    PlatformAuditTopIp(
                        ip_address=str(item.get("ip_address") or ""),
                        request_count=int(item.get("request_count") or 0),
                    )
                )

    dist_raw = raw.get("event_distribution")
    event_distribution: list[PlatformAuditEventCount] = []
    if isinstance(dist_raw, list):
        for item in dist_raw:
            if isinstance(item, dict):
                event_distribution.append(
                    PlatformAuditEventCount(
                        event_type=str(item.get("event_type") or ""),
                        count=int(item.get("count") or 0),
                    )
                )

    success_failed_raw = raw.get("success_vs_failed")
    success = 0
    failed = 0
    if isinstance(success_failed_raw, dict):
        success = int(success_failed_raw.get("success") or 0)
        failed = int(success_failed_raw.get("failed") or 0)

    return PlatformAuditStatsResponse(
        time_series=time_series,
        top_ips=top_ips,
        event_distribution=event_distribution,
        success_vs_failed=PlatformAuditSuccessFailed(success=success, failed=failed),
        total_events=int(raw.get("total_events") or 0),
        time_range_hours=int(raw.get("time_range_hours") or 24),
        is_live=True,
    )


async def _fetch_cp_audit_logs(*, limit: int) -> PlatformAuditLogsResponse | None:
    base = get_cp_api_base()
    headers = get_cp_request_headers()
    if not base or not headers:
        return None

    url = f"{base}/api/internal/security/audit/logs"
    try:
        async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT) as client:
            response = await client.get(url, headers=headers, params={"limit": limit})
            if response.status_code in (403, 404, 503):
                return None
            response.raise_for_status()
            data = response.json()
    except Exception as exc:
        logger.warning("Control plane audit logs unavailable: %s", exc)
        return None

    if not isinstance(data, dict):
        return None

    raw_events = data.get("events")
    if not isinstance(raw_events, list):
        return PlatformAuditLogsResponse(events=[], total=0, is_live=True)

    events = [_map_cp_event(item) for item in raw_events if isinstance(item, dict)]
    total_raw = data.get("total")
    total = int(total_raw) if isinstance(total_raw, int) else len(events)
    return PlatformAuditLogsResponse(events=events, total=total, is_live=True)


async def _fetch_cp_audit_stats(*, hours: int) -> PlatformAuditStatsResponse | None:
    base = get_cp_api_base()
    headers = get_cp_request_headers()
    if not base or not headers:
        return None

    url = f"{base}/api/internal/security/audit/stats"
    try:
        async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT) as client:
            response = await client.get(url, headers=headers, params={"hours": hours})
            if response.status_code in (403, 404, 503):
                return None
            response.raise_for_status()
            data = response.json()
    except Exception as exc:
        logger.warning("Control plane audit stats unavailable: %s", exc)
        return None

    if not isinstance(data, dict):
        return None
    return _map_cp_stats(data)


async def fetch_platform_audit_logs(*, limit: int = 100) -> PlatformAuditLogsResponse:
    if is_sandbox():
        cp_logs = await _fetch_cp_audit_logs(limit=limit)
        if cp_logs is not None:
            return cp_logs
        return PlatformAuditLogsResponse(events=[], total=0, is_live=False)

    try:
        events = read_auth_audit_events()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read audit logs: {exc}") from exc

    mapped = _map_auth_events(events, limit=limit)
    return PlatformAuditLogsResponse(events=mapped, total=len(mapped), is_live=True)


async def fetch_platform_audit_stats(*, hours: int = 24) -> PlatformAuditStatsResponse:
    if is_sandbox():
        cp_stats = await _fetch_cp_audit_stats(hours=hours)
        if cp_stats is not None:
            return cp_stats
        return PlatformAuditStatsResponse(
            time_series=[],
            top_ips=[],
            event_distribution=[],
            success_vs_failed=PlatformAuditSuccessFailed(success=0, failed=0),
            total_events=0,
            time_range_hours=hours,
            is_live=False,
        )

    try:
        events = read_auth_audit_events()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read audit logs: {exc}") from exc

    return _build_auth_stats(events, hours=hours)


async def export_platform_audit_logs(*, export_format: Literal["csv", "json"]) -> Response:
    logs = await fetch_platform_audit_logs(limit=1000)
    if not logs.events:
        raise HTTPException(status_code=404, detail="No audit log entries found")

    if export_format == "json":
        payload = [event.model_dump(by_alias=True) for event in logs.events]
        return Response(
            content=json.dumps(payload, ensure_ascii=False, indent=2),
            media_type="application/json",
            headers={"Content-Disposition": "attachment; filename=platform_audit.json"},
        )

    output = io.StringIO()
    fieldnames = [
        "event_type",
        "timestamp",
        "severity",
        "user_id",
        "sandbox_id",
        "result",
        "ip_address",
        "action",
        "source",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for event in logs.events:
        writer.writerow(
            {
                "event_type": event.event_type,
                "timestamp": event.timestamp,
                "severity": event.severity,
                "user_id": event.user_id or "",
                "sandbox_id": event.sandbox_id or "",
                "result": event.result,
                "ip_address": event.ip_address or "",
                "action": event.action,
                "source": event.source,
            }
        )

    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=platform_audit.csv"},
    )
