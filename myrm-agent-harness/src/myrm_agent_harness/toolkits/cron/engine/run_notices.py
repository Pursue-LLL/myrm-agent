"""Notices the executor raises about a job: a delivered run's outcome, a run a crash cut short and an automatic pause.

[INPUT]
- toolkits.cron.protocols::CronNoticeCallback (POS: Protocols for the cron toolkit.)
- toolkits.cron.types::CronJob, CronNotice, CronNoticeKind, DeliveryStatus, JobResult (POS: Cron job domain types.)

[OUTPUT]
- RunNoticeMixin: `emit_notice`, `_notify_run_outcome`, `notify_paused` and `notify_interrupted`, mixed into the executor

[POS]
Mixed into ``JobExecutor``. The engine reports facts only (the kind of notice, the job's name, a snippet of the
outcome); severity, wording, language and the name's presentation belong to the application layer's callback. A run
the loop guard cut off is announced by the pause it causes alone, and a run a crash cut short by a notice of its own
that carries no text. A callback that raises is logged and never fails a run or a scheduler tick.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from myrm_agent_harness.toolkits.cron.types import CronJob, CronNotice, CronNoticeKind, DeliveryStatus, JobResult

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.cron.protocols import CronNoticeCallback

logger = logging.getLogger(__name__)

_OUTCOME_SNIPPET_CHARS = 100


class RunNoticeMixin:
    """Notice emission for ``JobExecutor``.

    Accesses JobExecutor members via self: _on_notice.
    """

    _on_notice: CronNoticeCallback | None

    async def emit_notice(self, notice: CronNotice) -> None:
        """Hand a notice to the application layer; a callback that raises is logged, never propagated."""
        if self._on_notice is None:
            return
        try:
            await self._on_notice(notice)
        except Exception as exc:
            logger.warning("Cron notice %s for job %r was not delivered: %s", notice.kind, notice.job_name, exc)

    async def _notify_run_outcome(
        self, job: CronJob, result: JobResult, delivery_status: DeliveryStatus, *, manual: bool
    ) -> None:
        """Notice of a run's outcome; a run whose delivery was skipped (SILENT output, no change) stays quiet.

        A circuit break outside a manual run is told by the pause it causes (``notify_paused``), not here: the run's
        own error quotes the tool and the arguments the loop guard saw. A manual run pauses nothing, so its outcome
        is the only notice it gets.
        """
        if delivery_status == DeliveryStatus.SKIPPED or (result.circuit_broken and not manual):
            return

        outcome = (result.output or "") if result.success else (result.error or "unknown")
        await self.emit_notice(
            CronNotice(
                kind=CronNoticeKind.RUN_SUCCEEDED if result.success else CronNoticeKind.RUN_FAILED,
                job_name=job.name,
                text=outcome[:_OUTCOME_SNIPPET_CHARS],
                chat_id=job.chat_id,
            )
        )

    async def notify_paused(self, job: CronJob) -> None:
        """Notice that the scheduler paused ``job`` by itself because of a failure it could not recover from.

        The caller has judged that its own write made the pause: a job that was already paused is not news.
        """
        await self.emit_notice(CronNotice(kind=CronNoticeKind.JOB_PAUSED_BY_FAILURE, job_name=job.name))

    async def notify_interrupted(self, job: CronJob, paused: bool) -> None:
        """Notices of a run a crash cut short: no run closes it, so no outcome would ever report it.

        The interrupted run stays quiet for a job that delivers nowhere, as a run whose delivery was skipped does
        (``_try_deliver``). ``paused`` says the crash's counted failure paused the job: that is told whatever the
        delivery, after the interrupted run, in the order a closing write tells them.
        """
        if job.delivery.channel != "none":
            await self.emit_notice(
                CronNotice(kind=CronNoticeKind.RUN_INTERRUPTED, job_name=job.name, chat_id=job.chat_id)
            )
        if paused:
            await self.notify_paused(job)
