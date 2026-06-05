"""Application lifecycle management.

Manages background monitors: MemoryPressureMonitor, AuthAlert, MaintenanceScheduler,
HealthHistory. All monitors follow start/stop pattern for clean lifecycle.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from myrm_agent_harness.runtime.memory_pressure import MemoryPressureMonitor

logger = logging.getLogger(__name__)

_memory_pressure_monitor: MemoryPressureMonitor | None = None


def _health_report_status(report: object) -> str | None:
    if isinstance(report, dict):
        v = report.get("status")
        return str(v) if v is not None else None
    status = getattr(report, "status", None)
    return str(status) if status is not None else None


def _health_report_to_mapping(report: object) -> dict[str, object]:
    if isinstance(report, dict):
        return report
    return {
        "component_name": str(getattr(report, "component_name", "")),
        "status": str(getattr(report, "status", "")),
        "message": str(getattr(report, "message", "")),
        "fix_suggestion": str(getattr(report, "fix_suggestion", "")),
    }


_auth_alert_monitor_task: asyncio.Task[None] | None = None

_health_history_recorder_task: asyncio.Task[None] | None = None


async def start_auth_alert_monitor() -> None:
    """Start auth alert monitor only when there is an external attack surface.

    Skipped in Local (loopback-only) mode where auth audit has no value.
    """
    global _auth_alert_monitor_task

    from app.config.deploy_mode import is_webui_remote_mode
    from app.platform_utils.deployment_capabilities import get_deployment_capabilities

    caps = get_deployment_capabilities()
    if not (caps.enables_auth_audit or is_webui_remote_mode()):
        logger.debug("Auth alert monitor skipped (local mode, no external attack surface)")
        return

    if _auth_alert_monitor_task is not None:
        return

    from app.middleware.auth_alert import alert_monitor_loop

    _auth_alert_monitor_task = asyncio.create_task(alert_monitor_loop())
    logger.info("Auth alert monitor started (every 5 min)")


async def stop_auth_alert_monitor() -> None:
    """Stop auth alert monitor."""
    global _auth_alert_monitor_task

    if _auth_alert_monitor_task is None:
        return

    _auth_alert_monitor_task.cancel()
    try:
        await _auth_alert_monitor_task
    except asyncio.CancelledError:
        pass
    _auth_alert_monitor_task = None
    logger.info("Auth alert monitor stopped")


async def start_memory_pressure_monitor() -> None:
    """Initialize and start the global MemoryPressureMonitor.

    Must be called BEFORE start_maintenance_scheduler() so the scheduler
    can subscribe to pressure events automatically.
    """
    global _memory_pressure_monitor

    if _memory_pressure_monitor is not None:
        return

    from myrm_agent_harness.runtime.memory_pressure import init_memory_pressure_monitor

    _memory_pressure_monitor = init_memory_pressure_monitor()
    await _memory_pressure_monitor.start()
    logger.info(
        "Memory pressure monitor started (initial_level=%s, mem=%.1f%%)",
        _memory_pressure_monitor.current_level.name,
        _memory_pressure_monitor.current_memory_percent,
    )

    # Also start the high-fidelity resource monitor
    from myrm_agent_harness.runtime.resource_monitor import get_resource_monitor

    from app.services.event.app_event_bus import AppEvent, AppEventType, get_event_bus

    async def _on_metrics_collected(metrics: object) -> None:
        try:
            monitor = get_resource_monitor()
            get_event_bus().publish(
                AppEvent(
                    event_type=AppEventType.MEMORY_HISTORY_UPDATED,
                    data={"history": monitor.get_history()},
                )
            )
        except Exception as e:
            logger.debug(f"Failed to publish memory history event: {e}")

    monitor = get_resource_monitor()
    monitor.add_listener(_on_metrics_collected)
    await monitor.start()


async def stop_memory_pressure_monitor() -> None:
    """Stop the global MemoryPressureMonitor."""
    global _memory_pressure_monitor

    if _memory_pressure_monitor is None:
        return

    await _memory_pressure_monitor.stop()
    _memory_pressure_monitor = None

    # Also stop the high-fidelity resource monitor
    from myrm_agent_harness.runtime.resource_monitor import get_resource_monitor

    await get_resource_monitor().stop()

    logger.info("Memory pressure monitor stopped")


def get_memory_pressure_monitor_instance() -> MemoryPressureMonitor | None:
    """Get the lifecycle-managed monitor instance (for subscriber registration)."""
    return _memory_pressure_monitor


async def start_maintenance_scheduler() -> None:
    """Initialize the global adaptive maintenance scheduler.

    Selects the appropriate LoadSensor based on deployment mode:
    - LOCAL/Tauri: DeviceLoadSensor (cross-platform CPU/memory via psutil)
    - SANDBOX (SaaS): SaaSLoadSensor (API quota headroom + queue depth)

    Also subscribes to MemoryPressureMonitor if already initialized.
    """
    try:
        from myrm_agent_harness.runtime.maintenance import (
            DeviceLoadSensor,
            SaaSLoadSensor,
            init_maintenance_scheduler,
        )

        from app.platform_utils.deployment_capabilities import get_deployment_capabilities

        caps = get_deployment_capabilities()
        sensor = SaaSLoadSensor() if caps.is_sandbox_instance else DeviceLoadSensor()
        init_maintenance_scheduler(sensor)
        mode = "SaaS" if caps.is_sandbox_instance else "Device"
        logger.info("Maintenance scheduler initialized (sensor=%s)", mode)
    except Exception as e:
        logger.error("Maintenance scheduler initialization failed: %s", e)


async def _health_history_recorder_job() -> None:
    """Record current health status to database for historical trend analysis."""
    try:
        import json
        from datetime import datetime, timedelta

        from sqlalchemy import text

        from app.api.health.router import system_doctor
        from app.database.connection import get_session

        health_data = await system_doctor()

        harness_raw = health_data.get("harness", [])
        server_raw = health_data.get("server", [])
        harness_list: list[object] = harness_raw if isinstance(harness_raw, list) else []
        server_list: list[object] = server_raw if isinstance(server_raw, list) else []
        all_reports: list[object] = harness_list + server_list
        total_count = len(all_reports)

        if total_count == 0:
            logger.warning("Health history recorder: no health reports available")
            return

        pass_count = sum(1 for r in all_reports if _health_report_status(r) == "pass")
        overall_score = round((pass_count / total_count) * 100)

        fail_count = sum(1 for r in all_reports if _health_report_status(r) == "fail")
        if fail_count > 0:
            overall_status = "fail"
        elif overall_score < 80:
            overall_status = "warn"
        else:
            overall_status = "pass"

        component_reports_json = json.dumps(
            {
                "harness": [_health_report_to_mapping(r) for r in harness_list],
                "server": server_list,
            }
        )

        async with get_session() as session:
            await session.execute(
                text(
                    """INSERT INTO system_health_history 
                       (timestamp, overall_status, overall_score, component_reports) 
                       VALUES (:timestamp, :status, :score, :reports)"""
                ),
                {
                    "timestamp": datetime.utcnow(),
                    "status": overall_status,
                    "score": overall_score,
                    "reports": component_reports_json,
                },
            )
            await session.commit()

        cutoff_time = datetime.utcnow() - timedelta(days=7)
        async with get_session() as session:
            await session.execute(
                text("DELETE FROM system_health_history WHERE timestamp < :cutoff"),
                {"cutoff": cutoff_time},
            )
            await session.commit()

        logger.debug(
            "Health history recorded: score=%d, status=%s",
            overall_score,
            overall_status,
        )

        try:
            from app.services.event.app_event_bus import AppEvent, AppEventType, get_event_bus

            get_event_bus().publish(
                AppEvent(
                    event_type=AppEventType.HEALTH_STATUS_UPDATED,
                    data={
                        "overall_score": overall_score,
                        "overall_status": overall_status,
                    },
                )
            )
        except Exception as e:
            logger.debug(f"Failed to publish health status event: {e}")

    except Exception as e:
        logger.error("Health history recorder failed: %s", e, exc_info=True)


async def start_health_history_recorder() -> None:
    """Start health history recorder (every 3 minutes)."""
    global _health_history_recorder_task

    if _health_history_recorder_task is not None:
        logger.debug("Health history recorder already running")
        return

    async def recorder_loop() -> None:
        """Background loop that records health data every 3 minutes."""
        try:
            while True:
                try:
                    await _health_history_recorder_job()
                except Exception as e:
                    logger.error("Health history recorder job failed: %s", e, exc_info=True)

                await asyncio.sleep(180)
        except asyncio.CancelledError:
            logger.info("Health history recorder loop cancelled")
            raise

    _health_history_recorder_task = asyncio.create_task(recorder_loop())
    logger.info("Health history recorder started (every 3 minutes)")


async def stop_health_history_recorder() -> None:
    """Stop health history recorder."""
    global _health_history_recorder_task

    if _health_history_recorder_task is None:
        return

    _health_history_recorder_task.cancel()
    try:
        await _health_history_recorder_task
    except asyncio.CancelledError:
        pass
    _health_history_recorder_task = None
    logger.info("Health history recorder stopped")
