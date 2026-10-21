"""Auth alert engine — rule-based anomaly detection for auth audit logs.

Scans the JSONL audit log for suspicious patterns (e.g. brute-force attempts)
and creates persistent system notifications when thresholds are exceeded.
Deduplicates alerts within each hourly window to avoid notification flooding.

[INPUT]
- app.middleware.auth_audit::AUDIT_LOG_FILE (POS: Auth audit JSONL logger)
- app.services.system_notification_service::SystemNotificationService (POS: System notification persistence)

[OUTPUT]
- evaluate_auth_anomalies(): detect anomalies and return alerts
- alert_monitor_loop(): background task that checks periodically

[POS]
Auth anomaly detection engine. Scans audit logs for brute-force patterns,
creates deduplicated warning notifications. WebUI Remote / Sandbox only.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from typing import Literal

from app.middleware.auth_audit import AUDIT_LOG_FILE

logger = logging.getLogger(__name__)

FAILURE_THRESHOLD_PER_IP = 10
WINDOW_SECONDS = 3600

_alerted_keys: set[str] = set()
_alerted_window_hour: int = 0


@dataclass(frozen=True, slots=True)
class AuthAlert:
    """Detected auth anomaly."""

    alert_type: Literal["high_failure_rate_ip"]
    severity: Literal["medium", "high", "critical"]
    message: str
    target_ip: str
    failure_count: int


def _dedup_key(alert: AuthAlert) -> str:
    return f"{alert.alert_type}:{alert.target_ip}"


async def evaluate_auth_anomalies() -> list[AuthAlert]:
    """Scan audit log for anomalies within the last hour."""
    if not AUDIT_LOG_FILE.exists():
        return []

    window_start = time.time() - WINDOW_SECONDS

    failures_per_ip: dict[str, int] = {}
    try:
        with AUDIT_LOG_FILE.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if event.get("ts", 0) >= window_start and event.get("type") == "auth_failure":
                    ip = str(event.get("ip", "unknown"))
                    failures_per_ip[ip] = failures_per_ip.get(ip, 0) + 1
    except OSError as e:
        logger.error("Failed to read auth audit log: %s", e)
        return []

    alerts: list[AuthAlert] = []
    for ip, count in failures_per_ip.items():
        if count >= FAILURE_THRESHOLD_PER_IP:
            alerts.append(
                AuthAlert(
                    alert_type="high_failure_rate_ip",
                    severity="high",
                    message=f"Suspicious auth activity from {ip}: {count} failed attempts in last hour",
                    target_ip=ip,
                    failure_count=count,
                )
            )
    return alerts


async def _persist_alert(alert: AuthAlert) -> None:
    """Create a persistent system notification for the detected anomaly."""
    try:
        from app.services.infra.system_notification import SystemNotificationService

        await SystemNotificationService.create_notification(
            title="Security Alert: Suspicious Auth Activity",
            message=alert.message,
            type="warning",
            source="auth_alert",
            meta_data={
                "alert_type": alert.alert_type,
                "severity": alert.severity,
                "target_ip": alert.target_ip,
                "failure_count": alert.failure_count,
                "action_url": "/security",
            },
        )
    except Exception as e:
        logger.error("Failed to persist auth alert notification: %s", e)


async def alert_monitor_loop() -> None:
    """Background task: check for auth anomalies every 5 minutes."""
    global _alerted_keys, _alerted_window_hour

    while True:
        try:
            current_hour = int(time.time()) // WINDOW_SECONDS
            if current_hour != _alerted_window_hour:
                _alerted_keys = set()
                _alerted_window_hour = current_hour

            alerts = await evaluate_auth_anomalies()
            for alert in alerts:
                key = _dedup_key(alert)
                if key in _alerted_keys:
                    continue
                _alerted_keys.add(key)
                await _persist_alert(alert)
                logger.warning("AUTH ALERT: %s", alert.message)
        except Exception as e:
            logger.error("Alert monitor error: %s", e)

        await asyncio.sleep(300)


__all__ = ["evaluate_auth_anomalies", "alert_monitor_loop"]
