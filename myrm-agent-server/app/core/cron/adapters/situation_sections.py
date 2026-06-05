"""Concrete SituationSection implementations for heartbeat enrichment.

Each section queries a specific data source for changes since the last
heartbeat tick and returns a human-readable summary.  All sections are
fault-tolerant: exceptions are caught by the builder, and ``None``
return signals "nothing to report" (the section is silently omitted).

Registered in ``setup.py`` via ``build_situation_report_builder()``.

[INPUT]
- myrm_agent_harness.toolkits.cron.situation::SituationContext (POS: Situation Report — pluggable context aggregator for heartbeat ticks.)
- myrm_agent_harness.toolkits.cron.situation::SituationReportBuilder (POS: Situation Report — pluggable context aggregator for heartbeat ticks.)
- app.core.cron.adapters.setup::get_cron_store (POS: 组装入口，创建 CronScheduler + CronManager + CronStore 单例)

[OUTPUT]
- PendingRemindersSection: Lists pending reminders and time-sensitive tasks.
- SystemHealthSection: Reports basic system health indicators.
- PatternDiscoverySection: Surfaces recently discovered behavioral patterns.
- DailyWorkSummarySection: Surfaces yesterday's consolidated work summary for push notifications.
- build_situation_report_builder: Factory that creates and populates the builder with all server-layer sections.

[POS]
SituationSection concrete implementations for heartbeat enrichment.
Provides PendingReminders, SystemHealth, PatternDiscovery, and DailyWorkSummary sections, plus a builder factory.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from myrm_agent_harness.toolkits.cron.situation import (
    SituationContext,
    SituationReportBuilder,
)


class PendingRemindersSection:
    """Lists pending reminders and time-sensitive tasks from cron jobs."""

    name = "Pending Reminders"
    priority = 10

    async def build(self, ctx: SituationContext) -> str | None:
        from app.core.cron.adapters.setup import get_cron_store

        store = get_cron_store()
        jobs = await store.list_jobs(user_id=ctx.user_id, limit=50)

        from myrm_agent_harness.toolkits.cron.types import JobStatus, ScheduleKind

        now = datetime.now(timezone.utc)
        pending: list[str] = []
        for job in jobs:
            if job.status != JobStatus.ACTIVE:
                continue
            if job.name.startswith("__"):
                continue
            if job.schedule.kind == ScheduleKind.ONCE and job.next_run_at:
                delta = job.next_run_at - now
                hours = delta.total_seconds() / 3600
                if hours > 0:
                    pending.append(f'- "{job.name}" — triggers in {hours:.1f}h')
            elif job.schedule.kind in (ScheduleKind.CRON, ScheduleKind.INTERVAL):
                if job.consecutive_failures > 0:
                    pending.append(f'- "{job.name}" — {job.consecutive_failures} consecutive failures')

        if not pending:
            return None
        return "\n".join(pending)


class SystemHealthSection:
    """Reports system health only when anomalies are detected.

    Returns ``None`` when all tasks are healthy, enabling the
    heartbeat no-content skip optimization to avoid unnecessary
    LLM calls during quiet periods.
    """

    name = "System Health"
    priority = 50

    async def build(self, ctx: SituationContext) -> str | None:
        from app.core.cron.adapters.setup import get_cron_store

        store = get_cron_store()
        jobs = await store.list_jobs(user_id=ctx.user_id, limit=200)

        from myrm_agent_harness.toolkits.cron.types import JobStatus

        failed_jobs: list[str] = []
        for job in jobs:
            if job.status == JobStatus.ACTIVE and job.consecutive_failures >= 3:
                failed_jobs.append(f'- "{job.name}" — {job.consecutive_failures} consecutive failures')

        if not failed_jobs:
            return None

        return "\n".join(failed_jobs)


class PatternDiscoverySection:
    """Surfaces recently discovered cross-cycle behavioral patterns.

    Queries episodic events tagged as pattern_discovery and presents them
    to the agent so it can proactively inform the user during heartbeat.
    """

    name = "Behavioral Patterns"
    priority = 30

    async def build(self, ctx: SituationContext) -> str | None:
        from app.core.memory.adapters.setup import create_memory_manager, resolve_context_binding
        from app.services.agent.platform_config import require_platform_embedding_config

        embedding_cfg = await require_platform_embedding_config()

        binding = resolve_context_binding(
            namespaces=None,
            agent_id=ctx.agent_id,
            channel_id=None,
            conversation_id=None,
            task_id=None,
        )
        manager = await create_memory_manager(
            binding,
            embedding_cfg,
            approval_required=False,
        )

        from myrm_agent_harness.toolkits.memory.strategies.pattern_discovery import (
            get_recent_patterns,
        )

        patterns = await get_recent_patterns(manager, limit=3)
        if not patterns:
            return None

        parts = []
        for p in patterns:
            lines = p.strip().split("\n")
            for line in lines[:3]:
                parts.append(f"- {line.strip()}")

        return "\n".join(parts) if parts else None


class DailyWorkSummarySection:
    """Surfaces yesterday's consolidated work summary for daily push notifications.

    Queries Chat, ApprovalRecord, and CronRunModel for yesterday's activity
    and formats a concise text summary suitable for channel push (WeChat, Slack, etc.).
    """

    name = "Yesterday Summary"
    priority = 5

    async def build(self, ctx: SituationContext) -> str | None:
        from sqlalchemy import func, select

        from app.database.connection import get_session
        from app.database.models import Chat
        from app.database.models.approval import ApprovalRecord
        from app.database.models.cron import CronRunModel

        now = datetime.now(timezone.utc)
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)
        day_end = day_start + timedelta(days=1)

        async with get_session() as db:
            session_row = await db.execute(
                select(
                    func.count(),
                    func.coalesce(func.sum(Chat.total_tokens), 0),
                    func.coalesce(func.sum(Chat.total_usd), 0),
                ).where(
                    Chat.created_at >= day_start,
                    Chat.created_at < day_end,
                    Chat.deleted_at.is_(None),
                )
            )
            s_count, s_tokens, s_usd = session_row.one()

            approval_count = (
                await db.scalar(
                    select(func.count())
                    .select_from(ApprovalRecord)
                    .where(ApprovalRecord.created_at >= day_start, ApprovalRecord.created_at < day_end)
                )
                or 0
            )

            cron_count = (
                await db.scalar(
                    select(func.count())
                    .select_from(CronRunModel)
                    .where(CronRunModel.started_at >= day_start, CronRunModel.started_at < day_end)
                )
                or 0
            )

        if s_count == 0 and approval_count == 0 and cron_count == 0:
            return None

        lines = [f"- {s_count} sessions | {s_tokens:,} tokens | ${float(s_usd):.2f}"]
        if approval_count:
            lines.append(f"- {approval_count} approvals resolved")
        if cron_count:
            lines.append(f"- {cron_count} cron executions")
        return "\n".join(lines)


def build_situation_report_builder() -> SituationReportBuilder:
    """Factory: creates and populates the builder with all server-layer sections."""
    from app.core.commitment.section import PendingCommitmentsSection

    builder = SituationReportBuilder(token_budget=800)
    builder.register(PendingCommitmentsSection())
    builder.register(DailyWorkSummarySection())
    builder.register(PendingRemindersSection())
    builder.register(PatternDiscoverySection())
    builder.register(SystemHealthSection())
    return builder
