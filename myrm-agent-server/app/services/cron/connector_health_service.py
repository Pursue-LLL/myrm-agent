"""Connector health tracking and degradation aggregation service for cron automations.

Aggregates connector delivery health across all active cron jobs and historical runs.
Calculates error distributions, consecutive failure counts, and health statuses
(HEALTHY, DEGRADED, DOWN) with actionable recovery suggestions and instant self-healing support.

[INPUT]
- myrm_agent_harness.toolkits.cron.engine.connector_health (POS: Domain error classification and redaction)
- app.database.repositories.uow::UnitOfWork (POS: DB session management)

[OUTPUT]
- ConnectorHealthSummary: Aggregated health stats for a specific connector target
- ConnectorHealthService: Business service to query and manage connector health states

[POS]
Server business layer service for connector health perception and degradation observability.
"""

from __future__ import annotations

import logging
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

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ConnectorHealthSummary:
    """Summary of health and error metrics for a connector target."""

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

    def to_dict(self) -> dict[str, object]:
        return {
            "target": self.target,
            "channel": self.channel,
            "status": self.status.value,
            "total_deliveries": self.total_deliveries,
            "failed_deliveries": self.failed_deliveries,
            "consecutive_failures": self.consecutive_failures,
            "last_status_code": self.last_status_code,
            "last_error_category": self.last_error_category.value if self.last_error_category else None,
            "last_error_message": self.last_error_message,
            "last_delivery_at": self.last_delivery_at.isoformat() if self.last_delivery_at else None,
            "last_failed_at": self.last_failed_at.isoformat() if self.last_failed_at else None,
            "fix_suggestion": self.fix_suggestion,
            "bound_job_ids": list(self.bound_job_ids),
        }


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

            # 1. Fetch all cron jobs that have a configured outbound delivery
            jobs_stmt = select(CronJobModel)
            jobs_res = await db.execute(jobs_stmt)
            jobs = list(jobs_res.scalars().all())

            # Group jobs by redacted target / channel
            connectors_map: dict[str, dict[str, object]] = {}

            for job in jobs:
                delivery = job.delivery or {}
                channel = delivery.get("channel", "chat")
                raw_target = delivery.get("target") or ""
                if channel in ("chat", "silent", "none") or not raw_target:
                    continue

                redacted = redact_connector_url(raw_target)
                key = f"{channel}:{redacted}"
                if key not in connectors_map:
                    connectors_map[key] = {
                        "channel": channel,
                        "raw_target": raw_target,
                        "redacted_target": redacted,
                        "job_ids": [job.id],
                        "consecutive_failures": job.consecutive_failures,
                        "last_error": job.last_error,
                    }
                else:
                    item_job_ids = connectors_map[key]["job_ids"]
                    if isinstance(item_job_ids, list):
                        item_job_ids.append(job.id)
                    cur_cf = int(connectors_map[key]["consecutive_failures"])  # type: ignore[arg-type]
                    if job.consecutive_failures > cur_cf:
                        connectors_map[key]["consecutive_failures"] = job.consecutive_failures
                        connectors_map[key]["last_error"] = job.last_error

            if not connectors_map:
                return []

            # 2. For each connector, fetch recent run delivery history within window
            summaries: list[ConnectorHealthSummary] = []

            for _key, info in connectors_map.items():
                job_ids = info["job_ids"]
                if not isinstance(job_ids, list) or not job_ids:
                    continue

                runs_stmt = (
                    select(CronRunModel)
                    .where(
                        CronRunModel.job_id.in_(job_ids),
                        CronRunModel.started_at >= since,
                    )
                    .order_by(desc(CronRunModel.started_at))
                    .limit(50)
                )
                runs_res = await db.execute(runs_stmt)
                recent_runs = list(runs_res.scalars().all())

                total_deliveries = len(recent_runs)
                failed_deliveries = sum(
                    1 for r in recent_runs if r.delivery_status == "failed"
                )

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

                # Classification
                last_err_msg = last_failed_run.delivery_error if last_failed_run else (info["last_error"] if isinstance(info["last_error"], str) else None)
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
                        target=str(info["redacted_target"]),
                        channel=str(info["channel"]),
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
