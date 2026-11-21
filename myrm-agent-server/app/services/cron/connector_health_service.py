"""Connector health aggregation service for cron automations.

Aggregates delivery health per outbound target (channel plus redacted address) for every cron job that delivers to
one, whatever the job's status, from the delivery attempts in a sliding window of run history. Per target it derives
delivery counts, the consecutive-failure streak, the last error category and a health status (HEALTHY, DEGRADED,
DOWN) with an actionable fix suggestion.

[INPUT]
- myrm_agent_harness.toolkits.cron.engine.connector_health (POS: Domain error classification and redaction)
- app.database.models.cron::CronJobModel, CronRunModel (POS: Cron job and run persistence models)
- app.database.repositories.uow::UnitOfWork (POS: DB session management)

[OUTPUT]
- ConnectorHealthSummary: Aggregated health stats for a specific connector target
- ConnectorHealthService: Read-only service that aggregates delivery health per channel and redacted target

[POS]
Server business layer service for connector health perception and degradation observability.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from myrm_agent_harness.api import (
    ConnectorErrorCategory,
    ConnectorHealthStatus,
    classify_connector_error,
    generate_fix_suggestion,
    redact_connector_url,
)
from sqlalchemy import desc, select

from app.database.models.cron import CronJobModel, CronRunModel
from app.database.repositories.uow import UnitOfWork


@dataclass(frozen=True, slots=True)
class ConnectorHealthSummary:
    """Health of one outbound target, from the delivery attempts of the jobs that deliver to it.

    Only runs whose delivery was attempted (delivered or failed) count: a skipped delivery says nothing about the
    target, and a task's own failure is not the target's fault. Counts cover the latest 50 attempts in the window.
    ``last_delivery_at`` and ``last_failed_at`` are the finish times of the runs that made those attempts, taken
    before the delivery itself ran.
    """

    target: str
    channel: str
    status: ConnectorHealthStatus
    total_deliveries: int
    failed_deliveries: int
    consecutive_failures: int
    last_status_code: int | None = None
    last_error_category: ConnectorErrorCategory | None = None
    last_error_message: str | None = None
    last_delivery_at: datetime | None = None
    last_failed_at: datetime | None = None
    fix_suggestion: str | None = None
    bound_job_ids: tuple[str, ...] = field(default_factory=tuple)


class ConnectorHealthService:
    """Service to analyze and aggregate health status for external delivery destinations."""

    @staticmethod
    async def get_all_connectors_health(
        *,
        window_hours: int = 24,
    ) -> list[ConnectorHealthSummary]:
        """Aggregate health metrics for all configured connectors over a sliding window."""
        since = datetime.now(UTC) - timedelta(hours=window_hours)

        async with UnitOfWork() as uow:
            db = uow.session
            assert db is not None
            # 1. Group the ids of the jobs that deliver to an outbound target by (channel, redacted target). Every job
            # is read and filtered here: its status does not matter, its delivery attempts in the window do.
            jobs_res = await db.execute(select(CronJobModel))
            job_ids_by_target: dict[tuple[str, str], list[str]] = defaultdict(list)
            for job in jobs_res.scalars().all():
                delivery = job.delivery or {}
                channel = delivery.get("channel", "chat")
                raw_target = delivery.get("target") or ""
                if channel in ("chat", "silent", "none") or not raw_target:
                    continue
                job_ids_by_target[(channel, redact_connector_url(raw_target))].append(job.id)

            # 2. Per target, read its latest delivery attempts inside the window
            summaries: list[ConnectorHealthSummary] = []

            for (channel, redacted_target), job_ids in job_ids_by_target.items():
                runs_stmt = (
                    select(CronRunModel)
                    .where(
                        CronRunModel.job_id.in_(job_ids),
                        CronRunModel.started_at >= since,
                        CronRunModel.delivery_status.in_(("delivered", "failed")),
                    )
                    .order_by(desc(CronRunModel.started_at))
                    .limit(50)
                )
                runs_res = await db.execute(runs_stmt)
                recent_runs = list(runs_res.scalars().all())

                total_deliveries = len(recent_runs)
                failed_deliveries = sum(1 for r in recent_runs if r.delivery_status == "failed")

                # Determine consecutive delivery failures from most recent runs
                consecutive_failures = 0
                last_failed_run: CronRunModel | None = None
                last_delivery_run: CronRunModel | None = recent_runs[0] if recent_runs else None

                for r in recent_runs:
                    if r.delivery_status == "failed":
                        consecutive_failures += 1
                        if last_failed_run is None:
                            last_failed_run = r
                    elif r.delivery_status == "delivered":
                        break

                # Classification: only a failed delivery's own error describes the connector, a task's error does not
                last_err_msg = last_failed_run.delivery_error if last_failed_run else None
                last_cat: ConnectorErrorCategory | None = None
                fix_sug: str | None = None

                if last_err_msg:
                    last_cat, _ = classify_connector_error(last_err_msg)
                    fix_sug = generate_fix_suggestion(last_cat)

                # Health state calculation
                if consecutive_failures >= 3 or (last_cat == ConnectorErrorCategory.AUTH_FAILURE):
                    status = ConnectorHealthStatus.DOWN
                elif consecutive_failures > 0:
                    status = ConnectorHealthStatus.DEGRADED
                else:
                    status = ConnectorHealthStatus.HEALTHY

                summaries.append(
                    ConnectorHealthSummary(
                        target=redacted_target,
                        channel=channel,
                        status=status,
                        total_deliveries=total_deliveries,
                        failed_deliveries=failed_deliveries,
                        consecutive_failures=consecutive_failures,
                        last_error_category=last_cat,
                        last_error_message=last_err_msg,
                        last_delivery_at=last_delivery_run.finished_at if last_delivery_run else None,
                        last_failed_at=last_failed_run.finished_at if last_failed_run else None,
                        fix_suggestion=fix_sug,
                        bound_job_ids=tuple(job_ids),
                    )
                )

            return summaries


__all__ = [
    "ConnectorHealthService",
    "ConnectorHealthSummary",
]
