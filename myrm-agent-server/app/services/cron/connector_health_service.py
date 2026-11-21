"""Connector health aggregation service for cron automations.

Aggregates delivery health per outbound destination (a channel plus the exact address) for every cron job that
delivers to one, whatever the job's status, from the delivery attempts in a sliding window of run history. Per
destination it derives delivery counts, the consecutive-failure streak, the last error category and a health status
(HEALTHY, DEGRADED, DOWN).

[INPUT]
- myrm_agent_harness.toolkits.cron.engine.connector_health (POS: Domain error classification, destination identity and redaction)
- app.database.models.cron::CronJobModel, CronRunModel (POS: Cron job and run persistence models)
- app.database.repositories.uow::UnitOfWork (POS: DB session management)

[OUTPUT]
- ConnectorHealthSummary: Aggregated health stats for one delivery destination
- ConnectorHealthService: Read-only service that aggregates delivery health per destination

[POS]
Server business layer service for connector health perception and degradation observability.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from itertools import takewhile

from myrm_agent_harness.api import (
    ConnectorErrorCategory,
    ConnectorHealthStatus,
    classify_connector_error,
    delivery_target_key,
    redact_connector_url,
)
from sqlalchemy import desc, func, select

from app.database.models.cron import CronJobModel, CronRunModel
from app.database.repositories.uow import UnitOfWork

# Delivery attempts of one destination that the counts and the streak are read from, newest first.
_MAX_ATTEMPTS = 50
# A destination is DOWN once this many deliveries in a row have failed.
_DOWN_AFTER_FAILURES = 3


@dataclass(frozen=True, slots=True)
class ConnectorHealthSummary:
    """Health of one outbound destination, from the delivery attempts of the jobs that deliver to it.

    Only runs whose delivery was attempted (delivered or failed) count: a skipped delivery says nothing about the
    destination, and a task's own failure is not the destination's fault. Counts cover the latest 50 attempts in the
    window. ``last_delivery_at`` and ``last_failed_at`` are the finish times of the runs that made those attempts,
    taken before the delivery itself ran.
    """

    target: str
    channel: str
    status: ConnectorHealthStatus
    total_deliveries: int
    failed_deliveries: int
    consecutive_failures: int
    last_error_category: ConnectorErrorCategory | None = None
    last_error_message: str | None = None
    last_delivery_at: datetime | None = None
    last_failed_at: datetime | None = None
    bound_job_ids: tuple[str, ...] = field(default_factory=tuple)


@dataclass(slots=True)
class _Destination:
    """The jobs that deliver to one destination, with the redacted address to show for it."""

    channel: str
    target: str
    job_ids: list[str] = field(default_factory=list)


def _summarise(destination: _Destination, recent_runs: list[CronRunModel]) -> ConnectorHealthSummary:
    """Derive the health of a destination from its delivery attempts, newest first."""
    # The streak is the failed attempts since the last delivered one; a delivery ends it.
    streak = list(takewhile(lambda run: run.delivery_status == "failed", recent_runs))
    last_failed_run = streak[0] if streak else None

    # Only a failed delivery's own error describes the connector, a task's error does not.
    last_error_message = last_failed_run.delivery_error if last_failed_run else None
    last_category = classify_connector_error(last_error_message)[0] if last_error_message else None

    if len(streak) >= _DOWN_AFTER_FAILURES or last_category == ConnectorErrorCategory.AUTH_FAILURE:
        status = ConnectorHealthStatus.DOWN
    elif streak:
        status = ConnectorHealthStatus.DEGRADED
    else:
        status = ConnectorHealthStatus.HEALTHY

    return ConnectorHealthSummary(
        target=destination.target,
        channel=destination.channel,
        status=status,
        total_deliveries=len(recent_runs),
        failed_deliveries=sum(1 for run in recent_runs if run.delivery_status == "failed"),
        consecutive_failures=len(streak),
        last_error_category=last_category,
        last_error_message=last_error_message,
        last_delivery_at=recent_runs[0].finished_at if recent_runs else None,
        last_failed_at=last_failed_run.finished_at if last_failed_run else None,
        bound_job_ids=tuple(destination.job_ids),
    )


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
            # 1. Group the jobs that deliver to an outbound destination by the destination's key. Every job is read
            # and filtered here: its status does not matter, its delivery attempts in the window do.
            jobs_res = await db.execute(select(CronJobModel))
            destinations: dict[str, _Destination] = {}
            for job in jobs_res.scalars().all():
                delivery = job.delivery or {}
                channel = delivery.get("channel", "chat")
                raw_target = delivery.get("target")
                key = delivery_target_key(channel, raw_target)
                if not key:
                    continue
                destination = destinations.setdefault(key, _Destination(channel, redact_connector_url(raw_target)))
                destination.job_ids.append(job.id)

            # 2. Per destination, read its latest delivery attempts inside the window. The run's own key matters as
            # well as its job: a job that was re-pointed has attempts at its earlier destination in the same history.
            summaries: list[ConnectorHealthSummary] = []
            for key, destination in destinations.items():
                runs_stmt = (
                    select(CronRunModel)
                    .where(
                        CronRunModel.job_id.in_(destination.job_ids),
                        CronRunModel.started_at >= since,
                        CronRunModel.delivery_status.in_(("delivered", "failed")),
                        func.json_extract(CronRunModel.metadata_json, "$.delivery_key") == key,
                    )
                    .order_by(desc(CronRunModel.started_at))
                    .limit(_MAX_ATTEMPTS)
                )
                runs_res = await db.execute(runs_stmt)
                summaries.append(_summarise(destination, list(runs_res.scalars().all())))

            return summaries


__all__ = [
    "ConnectorHealthService",
    "ConnectorHealthSummary",
]
