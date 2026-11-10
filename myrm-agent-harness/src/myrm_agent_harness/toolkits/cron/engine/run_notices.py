"""Notices the executor raises about a job: a delivered run's outcome and an automatic pause.

[INPUT]
- toolkits.cron.protocols::CronNoticeCallback (POS: Protocols for the cron toolkit.)
- toolkits.cron.types::CronJob, CronNotice, CronNoticeKind, DeliveryStatus, JobResult (POS: Cron job domain types.)

[OUTPUT]
- RunNoticeMixin: `emit_notice` and `_notify_run_outcome`, mixed into the executor

[POS]
Mixed into ``JobExecutor``. The engine reports facts only (the kind of notice, the job's name, a snippet of the
outcome); severity, wording and language belong to the application layer's callback. A callback that raises is
logged and never fails a run or a scheduler tick.
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

    async def _notify_run_outcome(self, job: CronJob, result: JobResult, delivery_status: DeliveryStatus) -> None:
        """Notice of a run's outcome; a run whose delivery was skipped (SILENT output, no change) stays quiet."""
        if delivery_status == DeliveryStatus.SKIPPED:
            return

        outcome = (result.output or "") if result.success else (result.error or "unknown")
        await self.emit_notice(
            CronNotice(
                kind=CronNoticeKind.RUN_SUCCEEDED if result.success else CronNoticeKind.RUN_FAILED,
                job_name=job.name,
                text=f"[{job.name}] {outcome[:_OUTCOME_SNIPPET_CHARS]}",
                chat_id=job.chat_id,
            )
        )
