"""Ops Aggregated Snapshot Service.

[INPUT]
- app.services.agent.gateway::get_agent_gateway (POS: Agent 执行网关)
- app.core.channel_bridge::get_channel_gateway (POS: 渠道网关单例)
- app.lifecycle.monitors::get_memory_pressure_monitor_instance (POS: 内存监控单例)
- app.services.agent.execution_cache::get_execution_cache (POS: 执行单元缓存单例)
- app.core.infra.health.health_snapshot::collect_health_snapshot (POS: 健康报告采集)
- app.database.connection::get_session (POS: 数据库异步 session 获取工厂)
- app.schemas.ops::* (POS: 快照响应 DTOs)

[OUTPUT]
- OpsAggregatedSnapshotService: 并发聚合全量运行态指标的无状态服务单例

[POS]
Server 业务层 Ops 聚合快照服务。为控制平面、桌面端和 CLI 工具提供高性能、零存储的系统全景观测快照。
"""

from __future__ import annotations

import asyncio
import logging
import platform
import resource
import sys
import time
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from app.config.deploy_mode import get_deploy_mode
from app.config.settings import settings
from app.database.connection import get_session
from app.database.models import Chat, SystemNotification
from app.database.models.approval import ApprovalRecord
from app.database.models.cron import CronRunModel
from app.schemas.ops import (
    OpsAggregatedSnapshot,
    OpsChannelInfo,
    OpsDoctorSummaryInfo,
    OpsGovernanceInfo,
    OpsLivenessInfo,
    OpsMemoryInfo,
    OpsResourceInfo,
    OpsSystemInfo,
    OpsUsageRadarInfo,
)

logger = logging.getLogger(__name__)

_BOOT_MONOTONIC = time.monotonic()


class OpsAggregatedSnapshotService:
    """Service to collect a full-spectrum operational snapshot with isolation & safety fallbacks."""

    @classmethod
    async def collect_snapshot(
        cls, *, include_doctor: bool = True
    ) -> OpsAggregatedSnapshot:
        """Collect all operational metrics concurrently.

        Uses isolated DB sessions and protected memory accesses so any individual
        component glitch gracefully degrades without failing the entire snapshot.
        """
        system_task = asyncio.create_task(cls._collect_system_info())
        liveness_task = asyncio.create_task(cls._collect_liveness_info())
        resources_task = asyncio.create_task(cls._collect_resource_info())
        channels_task = asyncio.create_task(cls._collect_channel_info())
        governance_task = asyncio.create_task(cls._collect_governance_info())
        usage_radar_task = asyncio.create_task(cls._collect_usage_radar_info())
        memory_task = asyncio.create_task(cls._collect_memory_info())
        doctor_task = (
            asyncio.create_task(cls._collect_doctor_summary())
            if include_doctor
            else None
        )

        system_res = await cls._safe_await(
            system_task, default=cls._fallback_system_info()
        )
        liveness_res = await cls._safe_await(
            liveness_task, default=cls._fallback_liveness_info()
        )
        resources_res = await cls._safe_await(
            resources_task, default=cls._fallback_resource_info()
        )
        channels_res = await cls._safe_await(
            channels_task, default=cls._fallback_channel_info()
        )
        governance_res = await cls._safe_await(
            governance_task, default=OpsGovernanceInfo()
        )
        usage_radar_res = await cls._safe_await(
            usage_radar_task, default=OpsUsageRadarInfo()
        )
        memory_res = await cls._safe_await(
            memory_task, default=cls._fallback_memory_info()
        )
        doctor_res = (
            await cls._safe_await(doctor_task, default=None) if doctor_task else None
        )

        return OpsAggregatedSnapshot(
            system=system_res,
            liveness=liveness_res,
            resources=resources_res,
            channels=channels_res,
            governance=governance_res,
            usage_radar=usage_radar_res,
            memory=memory_res,
            doctor_summary=doctor_res,
        )

    @staticmethod
    async def _safe_await[T](task: asyncio.Task[T], default: T) -> T:
        try:
            return await task
        except Exception as exc:
            logger.warning("Ops snapshot subtask failed: %s", exc)
            return default

    @classmethod
    async def _collect_system_info(cls) -> OpsSystemInfo:
        deploy_mode = get_deploy_mode().value
        uptime = round(time.monotonic() - _BOOT_MONOTONIC, 1)
        return OpsSystemInfo(
            app_name=settings.app_name,
            app_version=settings.app_version,
            deploy_mode=deploy_mode,
            os=f"{platform.system()} {platform.release()}",
            python_version=platform.python_version(),
            uptime_seconds=uptime,
            timestamp_utc=datetime.now(UTC).isoformat(),
        )

    @classmethod
    async def _collect_liveness_info(cls) -> OpsLivenessInfo:
        from app.services.agent.gateway import get_agent_gateway

        gateway = get_agent_gateway()
        active_sessions = gateway.get_active_sessions()
        active_count = gateway.active_count
        max_concurrent = gateway.config.max_per_user
        available_slots = gateway.get_available_slots()

        pending_outbound = 0
        try:
            from app.core.channel_bridge import get_channel_gateway

            gw = get_channel_gateway()
            if (
                gw
                and gw.bus
                and hasattr(gw.bus, "durable_outbound")
                and gw.bus.durable_outbound
            ):
                pending_outbound = await gw.bus.durable_outbound.count_pending()
        except Exception:
            pass

        channels_summary = cls._get_channels_dict()
        has_degraded = any(
            ch.get("status") in ("degraded", "error")
            for ch in channels_summary.values()
        )

        if gateway.is_draining:
            state = "draining"
        elif active_count > 0:
            state = "busy"
        elif has_degraded:
            state = "degraded"
        else:
            state = "idle"

        return OpsLivenessInfo(
            state=state,
            active_sessions_count=active_count,
            active_sessions=active_sessions,
            available_slots=available_slots,
            max_concurrent=max_concurrent,
            is_draining=gateway.is_draining,
            pending_outbound_count=pending_outbound,
        )

    @classmethod
    async def _collect_resource_info(cls) -> OpsResourceInfo:
        rss_mb: float | None = None
        try:
            usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            scale = 1024.0 * 1024.0 if sys.platform == "darwin" else 1024.0
            rss_mb = round(usage / scale, 1)
        except Exception:
            pass

        memory_level = "unknown"
        memory_percent = 0.0
        try:
            from app.lifecycle.monitors import get_memory_pressure_monitor_instance

            monitor = get_memory_pressure_monitor_instance()
            if monitor is not None:
                memory_level = monitor.current_level.name
                memory_percent = round(monitor.current_memory_percent, 1)
        except Exception:
            pass

        idle_seconds = 1800.0
        warm_units = 0
        reclaimed_units = 0
        try:
            from app.services.agent.execution_cache import get_execution_cache

            cache = get_execution_cache()
            idle_seconds = getattr(cache, "idle_seconds", 1800.0)
            warm_units = getattr(cache, "warm_entry_count", 0)
            reclaimed_units = getattr(cache, "reclaimed_count", 0)
        except Exception:
            pass

        return OpsResourceInfo(
            process_rss_mb=rss_mb,
            memory_level=memory_level,
            memory_percent=memory_percent,
            idle_reclaim_timeout_seconds=idle_seconds,
            warm_execution_units=warm_units,
            reclaimed_execution_units=reclaimed_units,
        )

    @classmethod
    async def _collect_channel_info(cls) -> OpsChannelInfo:
        channels_map = cls._get_channels_dict()
        has_degraded = any(
            ch.get("status") in ("degraded", "error") for ch in channels_map.values()
        )
        return OpsChannelInfo(
            total_channels=len(channels_map),
            channels=channels_map,
            has_degraded_channel=has_degraded,
        )

    @classmethod
    def _get_channels_dict(cls) -> dict[str, dict[str, object]]:
        try:
            from app.core.channel_bridge import get_channel_gateway

            gw = get_channel_gateway()
            statuses = gw.get_status()
            return {name: {"status": status.value} for name, status in statuses.items()}
        except Exception:
            return {}

    @classmethod
    async def _collect_governance_info(cls) -> OpsGovernanceInfo:
        cron_failures = 0
        pending_approvals = 0
        unread_notifications = 0
        active_goals = 0

        async with get_session() as db:
            twenty_four_hours_ago = datetime.now(UTC) - timedelta(hours=24)
            try:
                cron_res = await db.scalar(
                    select(func.count())
                    .select_from(CronRunModel)
                    .where(
                        CronRunModel.status.in_(("failed", "error")),
                        CronRunModel.started_at >= twenty_four_hours_ago,
                    )
                )
                cron_failures = cron_res or 0
            except Exception:
                pass

            try:
                from myrm_agent_harness.toolkits.kanban.types import TaskStatus

                from app.services.kanban import KanbanService

                goal_pending = await db.scalar(
                    select(func.count())
                    .select_from(ApprovalRecord)
                    .where(ApprovalRecord.status == "PENDING")
                )
                kanban_review = (
                    await KanbanService.get_instance().count_tasks_by_status(
                        TaskStatus.IN_REVIEW
                    )
                )
                pending_approvals = (goal_pending or 0) + kanban_review
            except Exception:
                pass

            try:
                notif_res = await db.scalar(
                    select(func.count())
                    .select_from(SystemNotification)
                    .where(SystemNotification.is_read == False)  # noqa: E712
                )
                unread_notifications = notif_res or 0
            except Exception:
                pass

        try:
            from app.api.goals.router import _NON_TERMINAL_STATUSES
            from app.services.agent.goals.goal_registry import GoalRegistry

            with GoalRegistry._lock:
                session_ids = list(GoalRegistry._providers.keys())
            for sid in session_ids:
                provider = GoalRegistry.get_provider(sid)
                if not provider:
                    continue
                try:
                    goal = await provider.get_latest_goal(sid)
                    if goal and goal.status in _NON_TERMINAL_STATUSES:
                        active_goals += 1
                except Exception:
                    pass
        except Exception:
            pass

        extension_connected = False
        try:
            from app.services.extension.bridge import get_extension_bridge

            extension_connected = get_extension_bridge().is_connected()
        except Exception:
            pass

        return OpsGovernanceInfo(
            cron_failures_24h=cron_failures,
            pending_approvals=pending_approvals,
            unread_notifications=unread_notifications,
            active_goals=active_goals,
            extension_connected=extension_connected,
        )

    @classmethod
    async def _collect_usage_radar_info(cls) -> OpsUsageRadarInfo:
        async with get_session() as db:
            try:
                stmt = select(
                    func.sum(Chat.total_calls).label("total_calls"),
                    func.sum(Chat.total_tokens).label("total_tokens"),
                    func.sum(Chat.total_usd).label("total_usd"),
                )
                result = await db.execute(stmt)
                row = result.first()
                if row:
                    return OpsUsageRadarInfo(
                        total_calls=int(row.total_calls or 0),
                        total_tokens=int(row.total_tokens or 0),
                        total_usd=round(float(row.total_usd or 0.0), 6),
                    )
            except Exception:
                pass
        return OpsUsageRadarInfo()

    @classmethod
    async def _collect_memory_info(cls) -> OpsMemoryInfo:
        storage_mode = "sqlite"
        health_status: Literal["healthy", "degraded", "critical", "unknown"] = "unknown"
        event_count = 0
        failed_event_count = 0
        queue_backlog = 0

        try:
            from app.config.deploy_mode import get_storage_mode

            storage_mode = get_storage_mode().value
        except Exception:
            pass

        try:
            from myrm_agent_harness.toolkits.memory import MemoryOperationEventModel
            from myrm_agent_harness.toolkits.memory.types import MemoryOperationStatus

            async with get_session() as db:
                event_cnt = await db.scalar(
                    select(func.count(MemoryOperationEventModel.id))
                )
                event_count = event_cnt or 0
                failed_cnt = await db.scalar(
                    select(func.count(MemoryOperationEventModel.id)).where(
                        MemoryOperationEventModel.status
                        == MemoryOperationStatus.FAILED.value
                    )
                )
                failed_event_count = failed_cnt or 0
                health_status = "healthy" if failed_event_count == 0 else "degraded"
        except Exception:
            pass

        return OpsMemoryInfo(
            health_status=health_status,
            storage_mode=storage_mode,
            event_count=event_count,
            failed_event_count=failed_event_count,
            queue_backlog=queue_backlog,
        )

    @classmethod
    async def _collect_doctor_summary(cls) -> OpsDoctorSummaryInfo:
        try:
            async with asyncio.timeout(2.0):
                from app.core.infra.health.health_snapshot import (
                    collect_health_snapshot,
                )

                snapshot = await collect_health_snapshot()
                harness_reports = snapshot.harness_reports
                server_reports = snapshot.server_reports

                harness_passed = sum(1 for r in harness_reports if r.status == "pass")
                harness_failed = sum(
                    1 for r in harness_reports if r.status in ("fail", "warn")
                )
                server_passed = sum(1 for r in server_reports if r.status == "pass")
                server_failed = sum(
                    1 for r in server_reports if r.status in ("fail", "warn")
                )

                has_fail = any(
                    r.status == "fail" for r in (*harness_reports, *server_reports)
                )
                has_warn = any(
                    r.status == "warn" for r in (*harness_reports, *server_reports)
                )

                status: Literal["pass", "warn", "fail"] = (
                    "fail" if has_fail else ("warn" if has_warn else "pass")
                )

                issues: list[dict[str, object]] = [
                    {
                        "component": r.component_name,
                        "status": r.status,
                        "message": r.message,
                    }
                    for r in (*harness_reports, *server_reports)
                    if r.status in ("fail", "warn")
                ]

                return OpsDoctorSummaryInfo(
                    harness_total=len(harness_reports),
                    harness_passed=harness_passed,
                    harness_failed=harness_failed,
                    server_total=len(server_reports),
                    server_passed=server_passed,
                    server_failed=server_failed,
                    status=status,
                    issues=issues,
                )
        except Exception as exc:
            logger.warning(
                "Doctor summary diagnostic collection timed out or failed: %s", exc
            )
            return OpsDoctorSummaryInfo(
                status="warn",
                issues=[
                    {
                        "component": "Doctor",
                        "status": "warn",
                        "message": f"Diagnostics timed out: {exc}",
                    }
                ],
            )

    @classmethod
    def _fallback_system_info(cls) -> OpsSystemInfo:
        return OpsSystemInfo(
            app_name=getattr(settings, "app_name", "MyrmAgent"),
            app_version=getattr(settings, "app_version", "1.0.0"),
            deploy_mode="unknown",
            os=f"{platform.system()} {platform.release()}",
            python_version=platform.python_version(),
            uptime_seconds=0.0,
            timestamp_utc=datetime.now(UTC).isoformat(),
        )

    @classmethod
    def _fallback_liveness_info(cls) -> OpsLivenessInfo:
        return OpsLivenessInfo(
            state="idle",
            active_sessions_count=0,
            active_sessions=[],
            available_slots=4,
            max_concurrent=4,
            is_draining=False,
            pending_outbound_count=0,
        )

    @classmethod
    def _fallback_resource_info(cls) -> OpsResourceInfo:
        return OpsResourceInfo(
            process_rss_mb=None,
            memory_level="unknown",
            memory_percent=0.0,
            idle_reclaim_timeout_seconds=1800.0,
            warm_execution_units=0,
            reclaimed_execution_units=0,
        )

    @classmethod
    def _fallback_channel_info(cls) -> OpsChannelInfo:
        return OpsChannelInfo(
            total_channels=0,
            channels={},
            has_degraded_channel=False,
        )

    @classmethod
    def _fallback_memory_info(cls) -> OpsMemoryInfo:
        return OpsMemoryInfo(
            health_status="unknown",
            storage_mode="sqlite",
            event_count=0,
            failed_event_count=0,
            queue_backlog=0,
        )
