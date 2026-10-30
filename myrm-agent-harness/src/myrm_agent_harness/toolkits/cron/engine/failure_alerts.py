"""Failure alerting for cron jobs: dual-layer (per-job + global) alert decision and delivery.

[INPUT]
- toolkits.cron.engine.helpers::resolve_failure_alert, should_send_failure_alert (POS: alert config resolution and throttling)
- toolkits.cron.protocols::ResultDelivery (POS: Protocols for the cron toolkit.)
- toolkits.cron.types::CronJob, JobResult, FailureAlertConfig, DeliveryConfig (POS: Cron job domain types.)

[OUTPUT]
- FailureAlertMixin: `_maybe_send_failure_alert` — alert a failed run according to the job's (or the global) alert config

[POS]
Mixed into ``JobExecutor``. Called after the closing write has decided the job's fate, so the alert text
describes the job's updated state: paused, retrying with backoff, or left for its next regular run when the
failed run is not safe to repeat (``JobResult.retry_safe`` is False). Such a failure is alerted without
waiting for ``FailureAlertConfig.after`` consecutive failures.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import replace as dc_replace
from typing import TYPE_CHECKING

from myrm_agent_harness.toolkits.cron.engine.helpers import (
    resolve_failure_alert,
    should_send_failure_alert,
)
from myrm_agent_harness.toolkits.cron.types import CronJob, JobResult, JobStatus

if TYPE_CHECKING:
    from datetime import datetime

    from myrm_agent_harness.toolkits.cron.protocols import ResultDelivery
    from myrm_agent_harness.toolkits.cron.types import DeliveryConfig, FailureAlertConfig

logger = logging.getLogger(__name__)


class FailureAlertMixin:
    """Failure-alert behaviour for ``JobExecutor``.

    Accesses JobExecutor members via self: _delivery, _global_failure_alert, _global_failure_delivery.
    """

    _delivery: ResultDelivery
    _global_failure_alert: FailureAlertConfig | None
    _global_failure_delivery: DeliveryConfig | None

    def _maybe_send_failure_alert(
        self,
        job: CronJob,
        failures: int,
        now: datetime,
        *,
        retry_safe: bool = True,
    ) -> None:
        alert_config = resolve_failure_alert(job, self._global_failure_alert)
        if not alert_config:
            return
        if not should_send_failure_alert(job, alert_config, now, immediate=not retry_safe):
            return

        job.last_failure_alert_at = now

        error_snippet = (job.last_error or "unknown error")[:200]
        alert_result = JobResult(
            success=True,
            output=(
                f'Cron job "{job.name}" failed {failures} consecutive times.\n'
                f"Last error: {error_snippet}\n\n"
                f"{_failure_outlook(job, retry_safe=retry_safe)}"
            ),
        )

        effective_delivery = alert_config.delivery or job.failure_delivery or self._global_failure_delivery
        alert_job = dc_replace(job, delivery=effective_delivery) if effective_delivery else job

        task = asyncio.create_task(self._delivery.deliver(alert_job, alert_result))
        task.add_done_callback(_log_alert_delivery_failure)
        logger.warning(
            "Failure alert sent for job %s (%d consecutive failures) via %s",
            job.id,
            failures,
            alert_job.delivery.channel,
        )


def _failure_outlook(job: CronJob, *, retry_safe: bool) -> str:
    """What happens to the job after a failure, as the alert tells it (reads the job's updated state)."""
    if job.status == JobStatus.PAUSED:
        return "The task has been auto-paused."
    if retry_safe:
        return "The task will retry with backoff."
    outlook = "The task is not re-run ahead of schedule."
    if job.next_run_at is not None:
        outlook += f" Its next regular run is at {job.next_run_at.isoformat()}."
    return outlook


def _log_alert_delivery_failure(task: asyncio.Task[None]) -> None:
    """Callback for failure alert delivery tasks — log errors instead of silently swallowing."""
    exc = task.exception() if not task.cancelled() else None
    if exc:
        logger.warning("Failure alert delivery failed: %s", exc)
