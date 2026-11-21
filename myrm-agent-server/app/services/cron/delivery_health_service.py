"""Delivery health of the destination a cron job delivers to.

The verdict is about the destination (a channel plus the exact address), not about one job: every job that delivers
there adds its delivery attempts in the last day, whatever its status. It is a failure streak, the category of the
latest failure and one of three states (HEALTHY, DEGRADED, DOWN); a destination with no attempt in the window has no
verdict.

[INPUT]
- myrm_agent_harness.api (POS: public facade; the delivery failure taxonomy and the identity of a destination)
- myrm_agent_harness.toolkits.cron.serialization::dict_to_delivery (POS: JSON dict <-> cron domain types)
- app.core.cron.adapters.delivery_resolver::NON_OUTBOUND_CHANNELS (POS: business-layer cron delivery rules; the channels that deliver nowhere outside)
- app.core.cron.adapters.sqlalchemy_mapping::as_utc (POS: ORM <-> domain mapping for cron models; timestamps as UTC)
- app.database.models.cron::CronJobModel, CronRunModel (POS: Cron job and run persistence models)
- app.database.repositories.uow::UnitOfWork (POS: DB session management)

[OUTPUT]
- DeliveryHealthStatus: HEALTHY / DEGRADED / DOWN
- DeliveryHealth: the verdict on one destination
- DeliveryHealthService: Read-only service that judges a destination from its delivery attempts

[POS]
Server business-layer service behind a job's delivery-health badge. The rule that turns failures into a state is
here; the harness only classifies a failure and names a destination.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from itertools import takewhile

from myrm_agent_harness.api import ConnectorErrorCategory, classify_connector_error, delivery_target_key
from myrm_agent_harness.toolkits.cron.serialization import dict_to_delivery
from myrm_agent_harness.toolkits.cron.types import DeliveryConfig
from sqlalchemy import desc, func, select

from app.core.cron.adapters.delivery_resolver import NON_OUTBOUND_CHANNELS
from app.core.cron.adapters.sqlalchemy_mapping import as_utc
from app.database.models.cron import CronJobModel, CronRunModel
from app.database.repositories.uow import UnitOfWork

# Delivery attempts of one destination that the verdict is read from, newest first, and how far back they may lie.
_MAX_ATTEMPTS = 50
_WINDOW = timedelta(hours=24)
# A destination is DOWN once this many deliveries in a row have failed.
_DOWN_AFTER_FAILURES = 3
# Failures no retry can fix, because the credential or the address itself has to change: one is enough for DOWN.
_PERMANENT_FAILURES = frozenset({ConnectorErrorCategory.AUTH_FAILURE, ConnectorErrorCategory.ADDRESS_REJECTED})


class DeliveryHealthStatus(StrEnum):
    """Health state of a delivery destination."""

    HEALTHY = "healthy"  # The latest delivery went through
    DEGRADED = "degraded"  # One or two deliveries in a row failed
    DOWN = "down"  # Three in a row failed, or the latest one was refused for good (credentials, address)


@dataclass(frozen=True, slots=True)
class DeliveryHealth:
    """What the delivery attempts to one destination say about it.

    Only runs whose delivery was attempted (delivered or failed) count: a skipped delivery says nothing about the
    destination, and a task's own failure is not the destination's fault. The failure fields describe the streak that
    ends at the newest attempt, so they are empty while that attempt went through; ``last_failed_at`` is when the run
    behind the newest failure finished (before its delivery ran).
    """

    status: DeliveryHealthStatus
    failure_streak: int
    last_error_category: ConnectorErrorCategory | None = None
    last_failed_at: datetime | None = None


def _destination_key(channel: str, target: str | None) -> str:
    """The key of the destination a delivery config names; empty for one that sends nothing outside."""
    return "" if channel in NON_OUTBOUND_CHANNELS else delivery_target_key(channel, target)


def _job_destination_key(delivery: dict[str, str | None] | None) -> str:
    """The key of the destination a job's stored delivery config names."""
    config = dict_to_delivery(delivery) or DeliveryConfig()
    return _destination_key(config.channel, config.target)


def _summarise(attempts: Sequence[CronRunModel]) -> DeliveryHealth | None:
    """Derive the health of a destination from its delivery attempts, newest first; None when there are none."""
    if not attempts:
        return None
    # The streak is the failed attempts since the last delivered one; a delivery ends it.
    streak = list(takewhile(lambda run: run.delivery_status == "failed", attempts))
    if not streak:
        return DeliveryHealth(DeliveryHealthStatus.HEALTHY, failure_streak=0)

    # Only a failed delivery's own error describes the destination, a task's error does not.
    newest_failure = streak[0]
    category = classify_connector_error(newest_failure.delivery_error)[0]
    down = len(streak) >= _DOWN_AFTER_FAILURES or category in _PERMANENT_FAILURES
    return DeliveryHealth(
        status=DeliveryHealthStatus.DOWN if down else DeliveryHealthStatus.DEGRADED,
        failure_streak=len(streak),
        last_error_category=category,
        last_failed_at=as_utc(newest_failure.finished_at),
    )


class DeliveryHealthService:
    """Judges the health of a delivery destination from the runs that delivered to it."""

    @staticmethod
    async def get_destination_health(channel: str, target: str | None) -> DeliveryHealth | None:
        """The health of the destination ``channel`` and ``target`` name.

        None when there is no verdict: the channel sends nothing outside the application, or no delivery to the
        destination was attempted in the last day.
        """
        key = _destination_key(channel, target)
        if not key:
            return None
        since = datetime.now(UTC) - _WINDOW

        async with UnitOfWork() as uow:
            db = uow.session
            assert db is not None
            # Every job is read and filtered here: its status does not matter, its delivery attempts in the window
            # do. Only the delivery column is read, which is all the key derives from.
            jobs = await db.execute(select(CronJobModel.id, CronJobModel.delivery))
            job_ids = [job_id for job_id, delivery in jobs if _job_destination_key(delivery) == key]
            if not job_ids:
                return None

            # The newest attempts by finish time, which the executor takes just before it delivers: runs of one job
            # can overlap, so the run that started last need not be the one that delivered last. The run's own key
            # matters as well as its job: a job that was re-pointed has attempts at its earlier destination in the
            # same history.
            runs = await db.execute(
                select(CronRunModel)
                .where(
                    CronRunModel.job_id.in_(job_ids),
                    CronRunModel.finished_at >= since,
                    CronRunModel.delivery_status.in_(("delivered", "failed")),
                    func.json_extract(CronRunModel.metadata_json, "$.delivery_key") == key,
                )
                .order_by(desc(CronRunModel.finished_at))
                .limit(_MAX_ATTEMPTS)
            )
            return _summarise(runs.scalars().all())


__all__ = [
    "DeliveryHealth",
    "DeliveryHealthService",
    "DeliveryHealthStatus",
]
