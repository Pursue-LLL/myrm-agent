"""Single-job execution lifecycle.

Orchestrates the complete lifecycle of a single cron job execution:
run → record → deliver → update state → failure alert.

The ``JobExecutor`` holds references to store, delivery, and push callback
but owns no scheduling state — that remains in ``CronScheduler``.

[INPUT]
- toolkits.cron.types::CronConfig, (POS: Cron job domain types.)
- toolkits.cron.protocols::CronStore, PreFlightConditionError (POS: Protocols for the cron toolkit.)
- toolkits.cron.delivery_guard::is_silent_output, (POS: Cron delivery guard.)
- infra.incremental.manager::IncrementalMonitorManager (POS: Incremental monitor lifecycle manager.)
- observability.tracing::TracingContext (POS: Request-scoped trace_id/session_id for log correlation.)
- toolkits.cron.engine.failure_alerts::FailureAlertMixin (POS: failure alert decision and delivery, mixed into the executor)
- toolkits.cron.engine.incremental_monitoring::IncrementalMonitoringMixin (POS: diff of a run's output against its baseline, mixed into the executor)

[OUTPUT]
- JobExecutor: Manages the complete lifecycle of a single job execution.

[POS]
Single-job execution lifecycle.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import secrets
from dataclasses import replace as dc_replace
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from myrm_agent_harness.infra.incremental.manager import IncrementalMonitorManager
from myrm_agent_harness.observability.tracing import TracingContext
from myrm_agent_harness.toolkits.cron.delivery_guard import is_silent_output
from myrm_agent_harness.toolkits.cron.engine.connector_health import (
    ConnectorFailureDetail,
    classify_connector_error,
    redact_connector_url,
)
from myrm_agent_harness.toolkits.cron.engine.failure_alerts import FailureAlertMixin
from myrm_agent_harness.toolkits.cron.engine.helpers import (
    classify_transient_error,
    error_backoff_ms,
)
from myrm_agent_harness.toolkits.cron.engine.helpers import (
    extract_telemetry as _extract_telemetry,
)
from myrm_agent_harness.toolkits.cron.engine.incremental_monitoring import IncrementalMonitoringMixin
from myrm_agent_harness.toolkits.cron.engine.integrity import (
    GENESIS_HASH,
    compute_integrity_hash,
)
from myrm_agent_harness.toolkits.cron.engine.job_freshness import adopt_latest
from myrm_agent_harness.toolkits.cron.engine.parser import compute_next_run
from myrm_agent_harness.toolkits.cron.engine.skipped_runs import SkippedRunMixin
from myrm_agent_harness.toolkits.cron.protocols import PreFlightConditionError
from myrm_agent_harness.toolkits.cron.types import (
    CronConfig,
    CronJob,
    CronRunRecord,
    DeliveryStatus,
    JobResult,
    JobStatus,
    RunStatus,
    ScheduleKind,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine

    from myrm_agent_harness.toolkits.cron.protocols import (
        CronStore,
        JobRunner,
        PreFlightCondition,
        ResultDelivery,
    )

    # (user_id, job_name, text, level) with an optional ``chat_id`` keyword.
    PushCallback = Callable[..., Coroutine[None, None, None]]

logger = logging.getLogger(__name__)

_SCHEDULE_ERROR_THRESHOLD = 3
_MAX_OUTPUT_CHARS = 8000
_MAX_CONTEXT_FROM_CHARS = 8000


def _output_hash(text: str) -> str:
    """SHA-256 hex digest (first 32 chars) of normalized output."""
    return hashlib.sha256(text.strip().encode()).hexdigest()[:32]


class JobExecutor(FailureAlertMixin, IncrementalMonitoringMixin, SkippedRunMixin):
    """Manages the complete lifecycle of a single job execution.

    Stateful only in the sense that it holds injected dependencies.
    All per-execution state is local to each ``run_and_record`` call.

    Integrates incremental monitoring: when enabled, computes delta between
    current output and baseline, skips delivery if no new content.
    """

    def __init__(
        self,
        store: CronStore,
        delivery: ResultDelivery,
        config: CronConfig | None = None,
        push_callback: PushCallback | None = None,
        pre_condition: PreFlightCondition | None = None,
    ) -> None:
        cfg = config or CronConfig()
        self._store = store
        self._delivery = delivery
        self._push_callback = push_callback
        self._pre_condition = pre_condition
        self._global_failure_delivery = cfg.failure_delivery
        self._global_failure_alert = cfg.failure_alert
        self._monitor_manager = IncrementalMonitorManager(store)
        self._monitor_failure_fallback_counts: dict[str, int] = {}

    async def run_and_record(
        self,
        job: CronJob,
        runner: JobRunner,
        *,
        context: str = "",
        trigger_source: str = "cron",
    ) -> None:
        """Execute a job, persist the run record, deliver results, update state."""
        trace_token = TracingContext.set_trace_id(TracingContext.generate_trace_id())
        session_token = TracingContext.set_session_id(job.id)
        try:
            await self._execute_job(job, runner, context=context, trigger_source=trigger_source)
        finally:
            TracingContext.reset_trace_id(trace_token)
            TracingContext.reset_session_id(session_token)

    async def _execute_job(
        self,
        job: CronJob,
        runner: JobRunner,
        *,
        context: str = "",
        trigger_source: str = "cron",
    ) -> None:
        """Core execution logic within TracingContext scope."""
        self._current_trigger_source = trigger_source

        # 1. Pre-flight Condition check
        if self._pre_condition and job.pre_condition_script:
            probe_started = datetime.now(UTC)
            try:
                should_run, injected_context = await self._pre_condition.evaluate(job)
            except PreFlightConditionError as exc:
                # A probe that cannot decide is a failed run, never a skip. Nothing ran, so the next regular slot
                # is the retry: repeating early would meet the same cause again and only hasten the auto-pause.
                logger.warning("Job %s pre-flight condition failed: %s", job.id, exc)
                failure = JobResult(success=False, error=f"Pre-flight probe failed: {exc}", retry_safe=False)
                await self._finish_run(job, failure, probe_started, trigger_source)
                return
            if not should_run:
                logger.info("Job %s skipped by pre-flight condition", job.id)
                await self._record_skipped_by_probe(job)
                return
            if injected_context:
                context = f"{injected_context}\n\n{context}" if context else injected_context

        context_from_text = await self._resolve_context_from(job)
        effective_context = (
            f"{context_from_text}\n\n{context}" if context_from_text and context else context_from_text or context
        )

        started = datetime.now(UTC)
        try:
            result = await asyncio.wait_for(
                runner.run(job, context=effective_context),
                timeout=job.timeout_seconds,
            )
        except TimeoutError:
            result = JobResult(
                success=False,
                error=f"Execution timed out after {job.timeout_seconds}s",
                exit_code=124,
                retry_safe=False,
            )
            logger.warning("Job %s timed out after %ds", job.id, job.timeout_seconds)

        if result.retry_at is not None:
            logger.info(
                "Job %s deferred until %s: %s",
                job.id,
                result.retry_at.isoformat(),
                result.skip_reason or result.error or "unknown",
            )
            await self._record_deferred(job, result)
            return

        if result.skipped:
            logger.info("Job %s skipped by runner: %s", job.id, result.skip_reason or "unknown")
            await self._record_skipped_by_runner(job, result.skip_reason)
            return

        await self._finish_run(job, result, started, trigger_source)

    async def _finish_run(
        self,
        job: CronJob,
        result: JobResult,
        started: datetime,
        trigger_source: str,
    ) -> None:
        """Close a run that reached a verdict: monitoring, delivery, the run record, the push, the job's new state."""
        finished = datetime.now(UTC)
        duration_ms = int((finished - started).total_seconds() * 1000)

        result = await self._apply_incremental_monitoring(job, result)

        model, usage_in, usage_out, usage_total = _extract_telemetry(result)
        delivery_status, delivery_error = await self._try_deliver(job, result)

        # Merge any connector failure detail attached during delivery into metadata
        run_metadata = dict(result.metadata) if isinstance(result.metadata, dict) else (result.metadata or None)
        if delivery_status == DeliveryStatus.FAILED and delivery_error:
            category, _ = classify_connector_error(delivery_error)
            target = redact_connector_url(job.delivery.target) if job.delivery else ""
            fail_detail = ConnectorFailureDetail(
                category=category,
                target=target,
                message=delivery_error[:500],
            )
            run_metadata = run_metadata or {}
            run_metadata.setdefault("connector_failure", fail_detail.to_dict())

        prev_hash = await self._store.get_latest_integrity_hash(job.id) or GENESIS_HASH

        run_status = (
            RunStatus.CIRCUIT_BREAK
            if getattr(result, "circuit_broken", False)
            else (RunStatus.OK if result.success else RunStatus.ERROR)
        )

        run = CronRunRecord(
            id=secrets.token_urlsafe(12),
            job_id=job.id,
            started_at=started,
            finished_at=finished,
            duration_ms=duration_ms,
            status=run_status,
            output=result.output[:_MAX_OUTPUT_CHARS] if result.output else None,
            error=result.error[:1000] if result.error else None,
            model=model,
            usage_input_tokens=usage_in,
            usage_output_tokens=usage_out,
            usage_total_tokens=usage_total,
            trigger_source=trigger_source,
            delivery_status=delivery_status,
            delivery_error=delivery_error,
            metadata=run_metadata,
            prev_hash=prev_hash,
        )
        integrity_hash = compute_integrity_hash(run, prev_hash)
        run = dc_replace(run, integrity_hash=integrity_hash)

        await self._store.save_run(run)
        await self._push_notification(job, result, delivery_status)

        new_failures = 0 if result.success else job.consecutive_failures + 1
        await self._update_after_run(job, result, new_failures, finished)

    # ------------------------------------------------------------------
    # Delivery
    # ------------------------------------------------------------------

    async def _try_deliver(
        self,
        job: CronJob,
        result: JobResult,
    ) -> tuple[DeliveryStatus, str | None]:
        if job.delivery.channel == "none":
            return DeliveryStatus.SKIPPED, None

        metadata = result.metadata or {}
        contract_error_kind = metadata.get("monitor_contract_error")
        failure_count_raw = metadata.get("monitor_failure_count")
        failure_count = (
            failure_count_raw
            if isinstance(failure_count_raw, int) and not isinstance(failure_count_raw, bool)
            else None
        )
        if (
            not result.success
            and contract_error_kind == "invalid_json_like_output"
            and failure_count is not None
            and failure_count > 1
        ):
            logger.info(
                "Job %s: repeated monitor contract error (%d), suppressing duplicate main delivery",
                job.id,
                failure_count,
            )
            return DeliveryStatus.SKIPPED, "monitor_contract_error_dedup"

        if result.success:
            if result.exit_code == 0 and job.monitor_config and job.monitor_config.enabled:
                if result.metadata and result.metadata.get("baseline_reset"):
                    logger.info(
                        "Job %s: baseline reset detected, delivering notification despite exit_code=0",
                        job.id,
                    )
                else:
                    logger.info("Job %s: exit_code=0, no new content — skipping delivery", job.id)
                    return DeliveryStatus.SKIPPED, "no_new_content"

            output_text = (result.output or "").strip()
            if not output_text:
                logger.info("Job %s: empty output — skipping delivery", job.id)
                return DeliveryStatus.SKIPPED, "empty_output"
            if is_silent_output(output_text):
                logger.warning("Job %s: [SILENT] response — skipping delivery", job.id)
                return DeliveryStatus.SKIPPED, "silent_response"

            if job.deduplicate and output_text:
                current_hash = _output_hash(output_text)
                if current_hash == job.last_output_hash:
                    logger.warning("Job %s: duplicate output — skipping delivery", job.id)
                    return DeliveryStatus.SKIPPED, "duplicate_output"

        delivery_result = result
        if result.incremental_delta:
            delivery_result = dc_replace(result, output=result.incremental_delta)
            logger.info(
                "Job %s: delivering incremental delta (%d bytes, original: %d bytes)",
                job.id,
                len(result.incremental_delta),
                len(result.output),
            )

        try:
            await self._delivery.deliver(job, delivery_result)
        except Exception as exc:
            logger.warning("Delivery failed for job %s: %s", job.id, exc)
            return DeliveryStatus.FAILED, str(exc)[:500]

        if job.deduplicate and result.success:
            output_text = (result.output or "").strip()
            if output_text:
                job.last_output_hash = _output_hash(output_text)

        return DeliveryStatus.DELIVERED, None

    async def _push_notification(
        self,
        job: CronJob,
        result: JobResult,
        delivery_status: DeliveryStatus,
    ) -> None:
        if not self._push_callback:
            return
        if delivery_status == DeliveryStatus.SKIPPED:
            return

        level = "success" if result.success else "error"
        snippet = (result.output or "")[:100] if result.success else (result.error or "unknown")[:100]
        text = f"[{job.name}] {snippet}"
        try:
            # Support both 4-arg and 5-arg (with chat_id kwarg) push callbacks
            try:
                await self._push_callback(job.user_id, job.name, text, level, chat_id=job.chat_id)
            except TypeError:
                await self._push_callback(job.user_id, job.name, text, level)
        except Exception as exc:
            logger.warning("Push notification failed for job %s: %s", job.id, exc)

    # ------------------------------------------------------------------
    # Context-from resolution
    # ------------------------------------------------------------------

    async def _resolve_context_from(self, job: CronJob) -> str:
        """Build injected context from referenced jobs' latest successful outputs."""
        if not job.context_from:
            return ""
        fragments: list[str] = []
        for ref_id in job.context_from:
            runs = await self._store.list_runs(ref_id, limit=1, status="ok")
            if not runs or not runs[0].output:
                continue
            ref_job = await self._store.get_job(ref_id)
            task_name = ref_job.name if ref_job else ref_id
            output = runs[0].output
            if len(output) > _MAX_CONTEXT_FROM_CHARS:
                output = output[:_MAX_CONTEXT_FROM_CHARS] + "\n[... output truncated ...]"
            fragments.append(f"## Output from task '{task_name}'\n\n{output}")
        return "\n\n---\n\n".join(fragments)

    # ------------------------------------------------------------------
    # State update after execution
    # ------------------------------------------------------------------

    async def _update_after_run(
        self,
        job: CronJob,
        result: JobResult,
        new_failures: int,
        finished: datetime,
    ) -> None:
        if not await adopt_latest(self._store, job):
            logger.info("Job %s was deleted during execution, skipping post-run update", job.id)
            return

        if job.schedule.kind == ScheduleKind.ONCE:
            await self._handle_once_completion(job, result, new_failures, finished)
            return

        if getattr(result, "circuit_broken", False):
            job.status = JobStatus.PAUSED
            job.next_run_at = None
            logger.warning(
                "Job %s auto-paused due to circuit break: %s",
                job.id,
                result.error,
            )
        elif not result.success and new_failures > job.max_retries:
            job.status = JobStatus.PAUSED
            job.next_run_at = None
            logger.warning(
                "Job %s auto-paused: %d consecutive failures (max_retries=%d)",
                job.id,
                new_failures,
                job.max_retries,
            )
        elif result.success or not result.retry_safe:
            try:
                job.next_run_at = compute_next_run(job.schedule, finished)
            except Exception as exc:
                self._handle_schedule_compute_error(job, exc, finished)
        else:
            backoff = error_backoff_ms(new_failures)
            job.next_run_at = finished + timedelta(milliseconds=backoff)

        job.last_run_at = finished
        job.last_status = (
            RunStatus.CIRCUIT_BREAK
            if getattr(result, "circuit_broken", False)
            else (RunStatus.OK if result.success else RunStatus.ERROR)
        )
        job.last_error = result.error if not result.success else None
        job.consecutive_failures = new_failures

        if result.success:
            job.last_failure_alert_at = None
        else:
            self._maybe_send_failure_alert(job, new_failures, finished, retry_safe=result.retry_safe)

        job.updated_at = datetime.now(UTC)
        await self._store.save_job(job)

    async def _handle_once_completion(
        self,
        job: CronJob,
        result: JobResult,
        new_failures: int,
        finished: datetime,
    ) -> None:
        if result.success and job.delete_after_run:
            await self._store.delete_job(job.id)
            return

        if result.success:
            job.status = JobStatus.COMPLETED
            job.consecutive_failures = 0
            job.last_failure_alert_at = None
        elif result.retry_safe and classify_transient_error(result.error or "") and new_failures <= job.max_retries:
            backoff = error_backoff_ms(new_failures)
            job.next_run_at = finished + timedelta(milliseconds=backoff)
            job.consecutive_failures = new_failures
            job.last_error = result.error
            logger.warning(
                "One-shot job %s: transient error, retrying in %dms (attempt %d/%d)",
                job.id,
                backoff,
                new_failures,
                job.max_retries,
            )
        else:
            job.status = JobStatus.PAUSED
            job.consecutive_failures = new_failures
            job.last_error = result.error
            self._maybe_send_failure_alert(job, new_failures, finished, retry_safe=result.retry_safe)

        if job.status != JobStatus.ACTIVE:
            job.next_run_at = None
        job.last_run_at = finished
        job.last_status = RunStatus.OK if result.success else RunStatus.ERROR
        job.updated_at = datetime.now(UTC)
        await self._store.save_job(job)

    def _handle_schedule_compute_error(self, job: CronJob, error: Exception, finished: datetime) -> None:
        """Handle schedule computation failure with fallback retry.

        Below threshold: sets a 60-second fallback next_run_at so the
        scheduler retries instead of leaving the job as a zombie.
        At threshold: auto-pauses the job.
        """
        job.consecutive_failures += 1
        if job.consecutive_failures >= _SCHEDULE_ERROR_THRESHOLD:
            job.status = JobStatus.PAUSED
            job.next_run_at = None
            logger.warning(
                "Job %s auto-paused: schedule expression keeps failing (%d times): %s",
                job.id,
                job.consecutive_failures,
                error,
            )
        else:
            job.next_run_at = finished + timedelta(seconds=60)
            logger.warning(
                "Job %s: schedule compute error (%s), will retry in 60s",
                job.id,
                error,
            )
