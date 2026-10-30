"""Incremental monitoring of cron job results: diff a successful run's output against its stored baseline.

[INPUT]
- infra.incremental.manager::IncrementalMonitorManager (POS: Incremental monitor lifecycle manager.)
- infra.incremental.hash_monitor::InvalidJsonLikeMonitorOutputError (POS: Hash monitor JSON-like contract error type.)
- toolkits.cron.types::CronJob, JobResult (POS: Cron job domain types.)

[OUTPUT]
- IncrementalMonitoringMixin: `_apply_incremental_monitoring` turns a run's output into its delta;
  `_next_monitor_failure_count` counts consecutive monitor failures, with an in-memory fallback

[POS]
Mixed into ``JobExecutor``. Runs between the runner and the closing steps. A successful run of a monitored job
leaves with exit code 0 (nothing new) or 1 (new content, carried in ``incremental_delta``); a monitor that
fails leaves the full output untouched, except for an invalid JSON-like output, which turns the run into a
failed one so the problem is visible. The consecutive failure count is persisted; when the store refuses it,
an in-memory count keeps the escalation steady.
"""

from __future__ import annotations

import logging
from dataclasses import replace as dc_replace
from typing import TYPE_CHECKING

from myrm_agent_harness.infra.incremental.hash_monitor import InvalidJsonLikeMonitorOutputError

if TYPE_CHECKING:
    from myrm_agent_harness.infra.incremental.manager import IncrementalMonitorManager
    from myrm_agent_harness.toolkits.cron.types import CronJob, JobResult

logger = logging.getLogger(__name__)


class IncrementalMonitoringMixin:
    """Incremental-monitoring behaviour for ``JobExecutor``.

    Accesses JobExecutor members via self: _monitor_manager, _monitor_failure_fallback_counts.
    """

    _monitor_manager: IncrementalMonitorManager
    _monitor_failure_fallback_counts: dict[str, int]

    async def _apply_incremental_monitoring(
        self,
        job: CronJob,
        result: JobResult,
    ) -> JobResult:
        """Apply incremental monitoring if enabled.

        Args:
            job: Job configuration.
            result: Raw execution result.

        Returns:
            Modified result with incremental_delta and adjusted exit_code.
        """
        if not job.monitor_config or not job.monitor_config.enabled:
            return result

        if not result.success:
            return result

        try:
            monitor, reset_reason = await self._monitor_manager.get_monitor(
                job.id,
                job.monitor_config,
            )

            is_baseline_run = monitor.is_baseline()
            delta = monitor.compute_delta(result.output)

            metadata = result.metadata or {}
            if reset_reason == "ttl_expired":
                metadata["baseline_reset"] = True
                metadata["reset_reason"] = reset_reason
                logger.info("Job %s: baseline expired and reset, establishing new baseline", job.id)
            elif is_baseline_run and reset_reason == "first_run":
                logger.info("Job %s: first run, establishing baseline", job.id)

            if not delta:
                logger.info(
                    "Job %s: no new content detected (baseline: %s)",
                    job.id,
                    is_baseline_run,
                )
                result = dc_replace(
                    result,
                    exit_code=0,
                    incremental_delta="",
                    metadata=metadata if metadata else None,
                )
            else:
                logger.info(
                    "Job %s: detected new content (%d bytes)",
                    job.id,
                    len(delta),
                )

                result = dc_replace(
                    result,
                    exit_code=1,
                    incremental_delta=delta,
                    metadata=metadata if metadata else None,
                )

            monitor.update_baseline(delta)
            await self._monitor_manager.save_monitor_state(
                job.id,
                monitor,
                job.monitor_config,
            )
            self._monitor_failure_fallback_counts.pop(job.id, None)

        except Exception as exc:
            if job.monitor_config:
                failure_count, failure_count_source = await self._next_monitor_failure_count(
                    job,
                    exc,
                )

                contract_error = isinstance(exc, InvalidJsonLikeMonitorOutputError)
                if contract_error:
                    metadata = dict(result.metadata or {})
                    metadata["monitor_contract_error"] = "invalid_json_like_output"
                    metadata["monitor_failure_count"] = failure_count
                    if failure_count_source != "persistent_state":
                        metadata["monitor_failure_count_source"] = failure_count_source
                    contract_error_message = (
                        "Monitoring output format is invalid and cannot be diffed safely. "
                        "Please adjust the task output format or model settings."
                    )
                    logger.warning(
                        "Job %s: monitor output contract error (invalid JSON-like content); emitting visible warning",
                        job.id,
                    )
                    result = dc_replace(
                        result,
                        success=False,
                        error=contract_error_message,
                        exit_code=2,
                        output=contract_error_message,
                        incremental_delta="",
                        metadata=metadata,
                    )

                if contract_error and failure_count < 3:
                    logger.warning(
                        "Incremental monitoring contract error for job %s (%d/%d): %s",
                        job.id,
                        failure_count,
                        3,
                        exc,
                    )
                elif failure_count >= 3:
                    logger.error(
                        "Monitor for job %s failed %d times consecutively (last failure: %s)",
                        job.id,
                        failure_count,
                        exc,
                    )
                else:
                    logger.warning(
                        "Incremental monitoring failed for job %s (%d/%d): %s (continuing with full output)",
                        job.id,
                        failure_count,
                        3,
                        exc,
                    )
            else:
                logger.warning(
                    "Incremental monitoring failed for job %s: %s (continuing with full output)",
                    job.id,
                    exc,
                )

        return result

    async def _next_monitor_failure_count(
        self,
        job: CronJob,
        error: Exception,
    ) -> tuple[int, str]:
        """Return consecutive monitor failure count with storage fallback.

        Returns:
            Tuple of (failure_count, source), where source is either
            ``persistent_state`` or ``memory_fallback``.
        """
        if not job.monitor_config:
            return 1, "memory_fallback"

        try:
            failure_count = await self._monitor_manager.record_monitor_failure(
                job.id,
                job.monitor_config,
                error,
            )
            self._monitor_failure_fallback_counts[job.id] = failure_count
            return failure_count, "persistent_state"
        except Exception as persist_exc:
            failure_count = self._monitor_failure_fallback_counts.get(job.id, 0) + 1
            self._monitor_failure_fallback_counts[job.id] = failure_count
            logger.error(
                "Job %s: failed to persist monitor failure count, using in-memory fallback (%d): %s",
                job.id,
                failure_count,
                persist_exc,
            )
            return failure_count, "memory_fallback"
