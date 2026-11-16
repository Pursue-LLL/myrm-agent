"""Scheduling, alert, and error helpers for the cron engine.

All public functions are pure (no I/O besides log lines) and safe to call from any context.

[INPUT]
- toolkits.cron.engine.parser::compute_next_run (POS: next-run calculation)
- toolkits.cron.types::ActiveHours, CronJob, CronNotice, CronNoticeKind, FailureAlertConfig, RunStatus, Schedule, ScheduleKind (POS: Cron job domain types.)

[OUTPUT]
- resolve_stagger_ms: Compute the effective stagger delay for a job.
- is_within_active_hours: Return True if *now* falls within the active window, or if no window is set.
- next_eligible_run: The slot to book as a job's next run, with cooldown, 60 s floor and active window applied.
- next_slot_or_retry: The slot to book for a recurring job, or a minute ahead when its schedule cannot be computed.
- auto_pause_notice: The notice for a pre-execution verdict that paused the job.
- run_status_of: The status a run's record and its job's last status carry.

[POS]
Pure engine helpers: stagger resolution, schedule-window and backoff checks, the next slot to book, the pre-execution
guards with the notice an automatic pause raises, the status a run carries, failure-alert resolution and telemetry
extraction.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from myrm_agent_harness.toolkits.cron.engine.parser import compute_next_run
from myrm_agent_harness.toolkits.cron.types import (
    CronNotice,
    CronNoticeKind,
    FailureAlertConfig,
    RunStatus,
    ScheduleKind,
)

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.cron.types import (
        ActiveHours,
        CronJob,
        FailureAlertConfig,
        JobResult,
        Schedule,
        TransientErrorKind,
    )

logger = logging.getLogger(__name__)

_DEFAULT_TOP_OF_HOUR_STAGGER_MS = 5 * 60 * 1000
# Candidates examined while looking for a slot inside the active window; a window that no slot of the schedule
# reaches (a daily 09:30 job restricted to the evening) must not loop forever.
_MAX_SLOT_SCAN = 2000
# The slot is booked before the run starts, so nothing paces a schedule that can fire faster than once a minute
# (an interval, or a cron with a seconds field) except this floor.
_MIN_RECURRING_GAP_S = 60
# A schedule that cannot be computed is booked again this far ahead; the closing write of a run counts the failure.
_SCHEDULE_ERROR_RETRY_S = 60

# ---------------------------------------------------------------------------
# UTC normalisation
# ---------------------------------------------------------------------------


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


# ---------------------------------------------------------------------------
# Stagger
# ---------------------------------------------------------------------------


def resolve_stagger_ms(job: CronJob) -> int:
    """Compute the effective stagger delay for a job.

    Explicit ``stagger_ms=0`` means exact timing (no delay).
    ``stagger_ms=None`` triggers smart defaults: cron expressions that
    fire at minute-0 (e.g. ``0 * * * *``, ``0 9 * * *``) get a 5-minute
    random window to avoid thundering-herd in multi-user Sandbox scenarios.
    """
    sched = job.schedule
    if sched.stagger_ms is not None:
        return max(0, sched.stagger_ms)

    if sched.kind != ScheduleKind.CRON or not sched.expr:
        return 0

    minute_field = sched.expr.strip().split()[0] if sched.expr.strip() else ""
    if minute_field == "0":
        return _DEFAULT_TOP_OF_HOUR_STAGGER_MS
    return 0


# ---------------------------------------------------------------------------
# Active hours
# ---------------------------------------------------------------------------


def is_within_active_hours(ah: ActiveHours | None, *, now: datetime | None = None) -> bool:
    """Return True if *now* falls within the active window, or if no window is set."""
    if ah is None:
        return True

    try:
        start_h, start_m = (int(x) for x in ah.start.split(":"))
        end_h, end_m = (int(x) for x in ah.end.split(":"))
    except (ValueError, AttributeError):
        return True

    start_min = start_h * 60 + start_m
    end_min = end_h * 60 + end_m

    if now is None:
        now = datetime.now(UTC)

    try:
        tz = ZoneInfo(ah.tz) if ah.tz else UTC
        local_now = now.astimezone(tz)
    except KeyError:
        local_now = now

    current_min = local_now.hour * 60 + local_now.minute

    if end_min > start_min:
        return start_min <= current_min < end_min
    # Cross-midnight: e.g. 22:00 -> 06:00
    return current_min >= start_min or current_min < end_min


# ---------------------------------------------------------------------------
# Pre-execution checks & state detection
# ---------------------------------------------------------------------------


def is_past_misfire_grace(job: CronJob, now: datetime) -> bool:
    """Return True if the job has missed its fire window beyond the grace period."""
    if job.next_run_at is None:
        return False
    grace = timedelta(seconds=job.misfire_grace_seconds)
    return (now - _ensure_utc(job.next_run_at)) > grace


def is_in_error_backoff(job: CronJob, now: datetime) -> bool:
    """Return True if the job is within an exponential-backoff window after failure.

    Used during startup recovery to avoid immediately retrying a failed task
    whose backoff period has not yet elapsed.
    """
    from myrm_agent_harness.toolkits.cron.types import RunStatus

    _max_backoff_ms = 3_600_000
    if job.last_status != RunStatus.ERROR or job.last_run_at is None:
        return False
    failures = max(job.consecutive_failures, 1)
    backoff_ms = min(job.retry_backoff_ms * (2 ** (failures - 1)), _max_backoff_ms)
    backoff_end = _ensure_utc(job.last_run_at) + timedelta(milliseconds=backoff_ms)
    return now < backoff_end


def pre_execution_check(job: CronJob, now: datetime) -> str | None:
    """Run pre-execution guards. Returns skip reason or None if runnable.

    Checks (in order): expiry -> max_fires -> cooldown.
    Side-effect: sets ``job.status = PAUSED`` for expiry / max_fires.
    """
    from myrm_agent_harness.toolkits.cron.types import JobStatus

    if job.expires_at and now >= _ensure_utc(job.expires_at):
        job.status = JobStatus.PAUSED
        return "expired"
    if job.max_fires is not None and job.fire_count >= job.max_fires:
        job.status = JobStatus.PAUSED
        return "max_fires_reached"
    if job.cooldown_seconds > 0 and job.last_run_at:
        elapsed = (now - _ensure_utc(job.last_run_at)).total_seconds()
        if elapsed < job.cooldown_seconds:
            return "cooldown_active"
    return None


def _can_fire_within_a_minute(schedule: Schedule) -> bool:
    """An interval, or a cron whose field count is not the minute-aligned five."""
    return schedule.kind == ScheduleKind.INTERVAL or len((schedule.expr or "").split()) != 5


def next_eligible_run(job: CronJob, after: datetime, *, last_run_at: datetime | None = None) -> datetime | None:
    """The slot to book as a job's next regular run: the first one after ``after`` that clears the cooldown and
    the floor and lies in the active window.

    Create, resume, schedule edits, run closing, skipped runs and recovery all book through this function, so a
    booked slot is one the dispatch guards accept. A one-shot names its own instant and nothing moves it.
    ``last_run_at`` stands in for the stored one when the closing write has not saved it yet. A 5-field cron is
    minute-aligned, so the floor is not applied to it: flooring against a run's finish time would skip slots.
    When no slot inside the window turns up within ``_MAX_SLOT_SCAN`` candidates, the last candidate comes back
    and the dispatch guards record it as skipped and book again.
    """
    if job.schedule.kind == ScheduleKind.ONCE:
        return compute_next_run(job.schedule, _ensure_utc(after))
    earliest = _ensure_utc(after)
    last = last_run_at or job.last_run_at
    if job.cooldown_seconds > 0 and last:
        earliest = max(earliest, _ensure_utc(last) + timedelta(seconds=job.cooldown_seconds))
    candidate = compute_next_run(job.schedule, earliest)
    if candidate is not None and _can_fire_within_a_minute(job.schedule):
        floor = earliest + timedelta(seconds=_MIN_RECURRING_GAP_S)
        if candidate < floor:
            candidate = floor if job.schedule.kind == ScheduleKind.INTERVAL else compute_next_run(job.schedule, floor)
    for _ in range(_MAX_SLOT_SCAN):
        if candidate is None or is_within_active_hours(job.active_hours, now=candidate):
            return candidate
        candidate = compute_next_run(job.schedule, candidate)
    return candidate


def next_slot_or_retry(job: CronJob, now: datetime) -> datetime:
    """The slot to book for a recurring job; one whose schedule cannot be computed is booked a minute ahead.

    Booking must never fail for the schedule's sake: the job keeps a next run time, and the closing write of its
    next run computes the slot again and counts the failure toward auto-pause.
    """
    try:
        slot = next_eligible_run(job, now)
    except Exception as exc:
        logger.warning("Job %s: schedule compute error (%s), will retry in %ds", job.id, exc, _SCHEDULE_ERROR_RETRY_S)
        slot = None
    return slot if slot is not None else now + timedelta(seconds=_SCHEDULE_ERROR_RETRY_S)


def auto_pause_notice(job: CronJob, skip_reason: str) -> CronNotice | None:
    """The notice for a ``pre_execution_check`` verdict that paused the job; None for a verdict that did not."""
    if skip_reason == "expired":
        return CronNotice(kind=CronNoticeKind.JOB_EXPIRED, job_name=job.name)
    if skip_reason == "max_fires_reached":
        return CronNotice(kind=CronNoticeKind.JOB_MAX_FIRES_REACHED, job_name=job.name, max_fires=job.max_fires)
    return None


def run_status_of(result: JobResult) -> RunStatus:
    """The status a run's record and its job's ``last_status`` carry: a circuit break outranks a plain failure."""
    if result.circuit_broken:
        return RunStatus.CIRCUIT_BREAK
    return RunStatus.OK if result.success else RunStatus.ERROR


# ---------------------------------------------------------------------------
# Failure alert resolution
# ---------------------------------------------------------------------------


def resolve_failure_alert(
    job: CronJob,
    global_config: FailureAlertConfig | None,
) -> FailureAlertConfig | None:
    """Merge per-job and global failure alert configs.

    Resolution order:
    1. ``job.failure_alert is False`` -> disabled, return None
    2. ``job.failure_alert`` is a config -> use it (fill missing from global)
    3. Fall back to ``global_config`` if enabled
    """

    job_cfg = job.failure_alert
    if job_cfg is False:
        return None
    if job_cfg is not None and not isinstance(job_cfg, bool):
        return FailureAlertConfig(
            enabled=True,
            after=job_cfg.after,
            cooldown_seconds=job_cfg.cooldown_seconds,
            delivery=job_cfg.delivery or (job.delivery if job.delivery.channel != "none" else None),
        )
    if global_config and global_config.enabled:
        return global_config
    return None


def should_send_failure_alert(
    job: CronJob,
    alert_config: FailureAlertConfig,
    now: datetime,
    *,
    immediate: bool = False,
) -> bool:
    """Determine whether a failure alert should fire right now.

    ``immediate`` marks a failure that will not be repeated ahead of schedule, so waiting for
    ``alert_config.after`` consecutive failures would only delay the news by whole schedule periods;
    the cooldown still applies.
    """
    if not immediate and job.consecutive_failures < alert_config.after:
        return False
    if job.last_failure_alert_at:
        elapsed = (now - _ensure_utc(job.last_failure_alert_at)).total_seconds()
        if elapsed < alert_config.cooldown_seconds:
            return False
    return True


# ---------------------------------------------------------------------------
# Error classification, backoff, telemetry
# ---------------------------------------------------------------------------

BACKOFF_SCHEDULE_MS: tuple[int, ...] = (
    30_000,
    60_000,
    300_000,
    900_000,
    3_600_000,
)

_TRANSIENT_PATTERNS: dict[str, tuple[str, ...]] = {
    "rate_limit": ("rate_limit", "rate limit", "429", "too many requests"),
    "overloaded": ("overloaded", "capacity", "resource_exhausted"),
    "network": ("network", "connection", "dns", "unreachable"),
    "timeout": ("timeout", "timed out", "deadline"),
    "server_error": ("500", "502", "503", "internal server"),
}


def classify_transient_error(error_text: str) -> TransientErrorKind | None:
    """Identify whether an error is transient (worth retrying) or permanent.

    Returns the ``TransientErrorKind`` if a known transient pattern is found
    in *error_text*, or ``None`` for permanent / unrecognised errors.
    """
    from myrm_agent_harness.toolkits.cron.types import TransientErrorKind

    lower = error_text.lower()
    for kind_value, patterns in _TRANSIENT_PATTERNS.items():
        if any(p in lower for p in patterns):
            return TransientErrorKind(kind_value)
    return None


def error_backoff_ms(consecutive_errors: int) -> int:
    """Look up the backoff delay (ms) for the given error count.

    Uses a 5-level schedule: 30s -> 1m -> 5m -> 15m -> 60m (capped).
    """
    idx = min(max(consecutive_errors - 1, 0), len(BACKOFF_SCHEDULE_MS) - 1)
    return BACKOFF_SCHEDULE_MS[idx]


def _safe_int(val: object) -> int | None:
    """Coerce a value to int if numeric, else None."""
    if isinstance(val, int):
        return val
    if isinstance(val, float):
        return int(val)
    return None


def extract_telemetry(
    result: JobResult,
) -> tuple[str | None, int | None, int | None, int | None]:
    """Extract model name and token usage from JobResult metadata."""
    meta = result.metadata
    if not meta:
        return None, None, None, None

    model = str(meta["model"]) if "model" in meta else None

    usage = meta.get("usage")
    if isinstance(usage, dict):
        return (
            model,
            _safe_int(usage.get("prompt_tokens")),
            _safe_int(usage.get("completion_tokens")),
            _safe_int(usage.get("total_tokens")),
        )
    return model, None, None, None
