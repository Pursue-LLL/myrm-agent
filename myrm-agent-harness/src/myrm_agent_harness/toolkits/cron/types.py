"""Cron job domain types.

Pure data definitions — no I/O, safe to import anywhere.
Consumed by scheduler, manager, tools, and application adapters.

[INPUT]
- infra.incremental.types::MonitorConfig (POS: Domain types for incremental monitoring.)

[OUTPUT]
- ScheduleKind: how a job is scheduled — by cron expression, at a fixed interval or once
- JobType: what a job runs — an agent prompt, a shell command, a router or a reminder
- JobStatus: whether a job is active, paused or completed
- RunStatus: how a run ended — ok, error, skipped or circuit break
- PauseReason: why the scheduler paused a job by itself after a failure — a circuit break, repeated run failures or a schedule that cannot be computed
- RunNowOutcome: what a manual-run request came to — started, or why it did not
- TransientErrorKind: Classifies transient errors for smart retry decisions.
- SYSTEM_JOB_NAME_PREFIX, is_system_job_name: which job names are reserved for jobs the application creates itself
- CronNoticeKind: what a notice reports — a run's outcome, a run a crash cut short or an automatic pause
- CronNotice: one user-facing fact about a job, handed to the application layer's notice callback

[POS]
Cron job domain types.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from myrm_agent_harness.infra.incremental.types import MonitorConfig
    from myrm_agent_harness.toolkits.cron.triggers import TriggerConfig


class ScheduleKind(StrEnum):
    CRON = "cron"
    INTERVAL = "interval"
    ONCE = "once"


class JobType(StrEnum):
    AGENT = "agent"
    SHELL = "shell"
    ROUTER = "router"
    REMINDER = "reminder"


class JobStatus(StrEnum):
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"


class RunStatus(StrEnum):
    OK = "ok"
    ERROR = "error"
    SKIPPED = "skipped"
    CIRCUIT_BREAK = "circuit_break"


class PauseReason(StrEnum):
    """Why the scheduler paused a job by itself after a failure; a job a person paused has none."""

    CIRCUIT_BREAK = "circuit_break"
    RUN_FAILURES = "run_failures"
    SCHEDULE_ERROR = "schedule_error"


class RunNowOutcome(StrEnum):
    """What a request for a manual run came to: the run started, or the reason it did not."""

    STARTED = "started"
    NOT_FOUND = "not_found"
    NOT_ACTIVE = "not_active"
    ALREADY_RUNNING = "already_running"


class TransientErrorKind(StrEnum):
    """Classifies transient errors for smart retry decisions."""

    RATE_LIMIT = "rate_limit"
    OVERLOADED = "overloaded"
    NETWORK = "network"
    TIMEOUT = "timeout"
    SERVER_ERROR = "server_error"


class SessionTarget(StrEnum):
    """Controls whether a cron job runs in an isolated or shared session.

    - ``ISOLATED``: each execution starts with a blank context.
    - ``MAIN``: reuses the bound web-chat session's history.
    - ``DAILY``: same-day executions share context via injected history;
      a fresh context is started each calendar day.
    """

    ISOLATED = "isolated"
    MAIN = "main"
    DAILY = "daily"


# A name with this prefix is reserved for a job the application creates itself, as the heartbeat's is: the manager
# refuses it to every other caller, and a job listing leaves such jobs out unless it asks for them.
SYSTEM_JOB_NAME_PREFIX = "__"


def is_system_job_name(name: str) -> bool:
    """Whether ``name`` is reserved for a job the application creates itself."""
    return name.startswith(SYSTEM_JOB_NAME_PREFIX)


# ---------------------------------------------------------------------------
# Value objects
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ActiveHours:
    """Optional window restricting when a job may execute.

    Times are in ``HH:MM`` 24-hour format.  Cross-midnight ranges
    (e.g. ``start="22:00", end="06:00"``) are supported.
    ``tz`` is an IANA timezone name (defaults to UTC).
    """

    start: str  # "09:00"
    end: str  # "18:00"
    tz: str = "UTC"


@dataclass(frozen=True, slots=True)
class DeliveryConfig:
    """How to deliver task execution results.

    ``channel`` is a plain string — the application layer defines valid values
    (e.g. "chat", "webhook", "feishu").  ``target`` carries an address when
    the channel requires one (webhook URL, phone number, etc.).

    ``thread_id`` optionally pins delivery into one thread/topic of the
    target (group chats, forum topics); None delivers to the default scope.

    ``secret`` is auto-generated for webhook channels, used as HMAC key.
    """

    channel: str = "chat"
    target: str | None = None
    secret: str | None = None
    thread_id: str | None = None


@dataclass(frozen=True, slots=True)
class FailureAlertConfig:
    """Per-job or global failure alerting configuration.

    When used as a global default, ``enabled`` controls the master switch.
    Per-job configs on ``CronJob.failure_alert`` ignore ``enabled`` (use
    ``Literal[False]`` to explicitly disable for a single job).
    """

    enabled: bool = True
    after: int = 3
    cooldown_seconds: int = 300
    delivery: DeliveryConfig | None = None


@dataclass(frozen=True, slots=True)
class CronConfig:
    """Global scheduler configuration.

    Single configuration object for ``CronScheduler`` and ``JobExecutor``.
    All fields have sensible defaults — zero-config is valid.
    """

    max_concurrent: int = 3
    failure_delivery: DeliveryConfig | None = None
    failure_alert: FailureAlertConfig | None = None

    def __post_init__(self) -> None:
        if self.max_concurrent > 100:
            raise ValueError("max_concurrent must be <= 100 to prevent resource exhaustion")


@dataclass(frozen=True, slots=True)
class Schedule:
    """Immutable schedule definition.

    ``stagger_ms`` adds a random delay in [0, stagger_ms) before each
    execution, preventing thundering-herd when many jobs share the same
    cron expression (e.g. ``0 * * * *``).  ``None`` means "use smart
    default" (auto-set for top-of-hour cron); ``0`` means exact timing.
    """

    kind: ScheduleKind
    expr: str | None = None
    tz: str | None = None
    interval_ms: int | None = None
    run_at: datetime | None = None
    stagger_ms: int | None = None

    def __post_init__(self) -> None:
        if self.kind == ScheduleKind.CRON and not self.expr:
            raise ValueError("cron schedule requires 'expr'")
        if self.kind == ScheduleKind.INTERVAL and (not self.interval_ms or self.interval_ms < 100):
            raise ValueError("interval_ms must be >= 100 to prevent CPU storms")
        if self.kind == ScheduleKind.ONCE and not self.run_at:
            raise ValueError("once schedule requires 'run_at'")
        if self.tz and self.kind != ScheduleKind.CRON:
            raise ValueError("'tz' only applies to cron schedules")
        if self.stagger_ms is not None and self.stagger_ms < 0:
            object.__setattr__(self, "stagger_ms", 0)


@dataclass(slots=True)
class CronJob:
    """In-memory representation of a cron job."""

    id: str
    name: str
    job_type: JobType
    schedule: Schedule
    status: JobStatus = JobStatus.ACTIVE

    prompt: str | None = None
    model: str | None = None
    chat_id: str | None = None
    agent_id: str | None = None
    project_id: str | None = None
    workflow_template_id: str | None = None
    workflow_template_args: dict[str, str] | None = None

    command: str | None = None

    context_from: tuple[str, ...] = ()

    required_capabilities: tuple[str, ...] = ()
    allowed_roots: tuple[str, ...] = ()
    tools_allowed: tuple[str, ...] | None = None
    skill_ids: tuple[str, ...] = ()

    max_retries: int = 2
    retry_backoff_ms: int = 30_000
    timeout_seconds: int = 300
    misfire_grace_seconds: int = 300
    cooldown_seconds: int = 0
    max_fires: int | None = None
    expires_at: datetime | None = None
    fire_count: int = 0
    session_target: SessionTarget = SessionTarget.ISOLATED

    delivery: DeliveryConfig = field(default_factory=DeliveryConfig)
    failure_delivery: DeliveryConfig | None = None
    failure_alert: FailureAlertConfig | Literal[False] | None = None
    active_hours: ActiveHours | None = None
    delete_after_run: bool = False
    run_retention_days: int = 30
    deduplicate: bool = False
    skip_if_active: bool = False
    last_output_hash: str | None = None
    monitor_config: MonitorConfig | None = None
    triggers: TriggerConfig | None = None
    pre_condition_script: str | None = None
    acceptance_criteria: tuple[dict[str, object], ...] = ()

    next_run_at: datetime | None = None
    last_run_at: datetime | None = None
    last_status: RunStatus | None = None
    last_error: str | None = None
    consecutive_failures: int = 0
    last_failure_alert_at: datetime | None = None
    # Set while the scheduler's own pause holds; resuming, or pausing by hand, clears it.
    paused_reason: PauseReason | None = None

    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if self.timeout_seconds < 10:
            raise ValueError("timeout_seconds must be >= 10 to prevent alert storms")
        if self.retry_backoff_ms < 100:
            raise ValueError("retry_backoff_ms must be >= 100 to prevent service overload")
        if self.max_retries > 10:
            raise ValueError("max_retries must be <= 10 to prevent resource waste")
        if self.max_fires is not None and self.max_fires < 1:
            raise ValueError("max_fires must be >= 1")


@dataclass(frozen=True, slots=True)
class CronJobPatch:
    """Partial update descriptor — only non-None fields are applied."""

    name: str | None = None
    status: JobStatus | None = None
    schedule: Schedule | None = None
    prompt: str | None = None
    model: str | None = None
    agent_id: str | None = None
    project_id: str | None = None
    clear_project_id: bool = False
    command: str | None = None
    workflow_template_id: str | None = None
    workflow_template_args: dict[str, str] | None = None
    clear_workflow_template: bool = False

    context_from: tuple[str, ...] | None = None
    clear_context_from: bool = False
    pre_condition_script: str | None = None
    clear_pre_condition_script: bool = False

    required_capabilities: tuple[str, ...] | None = None
    allowed_roots: tuple[str, ...] | None = None
    tools_allowed: tuple[str, ...] | None = None
    clear_tools_allowed: bool = False
    skill_ids: tuple[str, ...] | None = None
    clear_skill_ids: bool = False
    delivery: DeliveryConfig | None = None
    failure_delivery: DeliveryConfig | None = None
    clear_failure_delivery: bool = False
    failure_alert: FailureAlertConfig | Literal[False] | None = None
    clear_failure_alert: bool = False
    active_hours: ActiveHours | None = None
    clear_active_hours: bool = False
    max_retries: int | None = None
    retry_backoff_ms: int | None = None
    timeout_seconds: int | None = None
    misfire_grace_seconds: int | None = None
    cooldown_seconds: int | None = None
    max_fires: int | None = None
    clear_max_fires: bool = False
    expires_at: datetime | None = None
    clear_expires_at: bool = False
    session_target: SessionTarget | None = None
    chat_id: str | None = None
    clear_chat_id: bool = False
    delete_after_run: bool | None = None
    run_retention_days: int | None = None
    deduplicate: bool | None = None
    skip_if_active: bool | None = None
    monitor_config: MonitorConfig | None = None
    clear_monitor_config: bool = False
    triggers: TriggerConfig | None = None
    clear_triggers: bool = False
    acceptance_criteria: tuple[dict[str, object], ...] | None = None
    clear_acceptance_criteria: bool = False


class DeliveryStatus(StrEnum):
    DELIVERED = "delivered"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass(frozen=True, slots=True)
class CronRunRecord:
    """Immutable record of a single job execution.

    ``metadata`` carries structured data collected during execution
    (e.g. blockedActions, progressSteps, sources).
    """

    id: str
    job_id: str
    started_at: datetime
    finished_at: datetime
    duration_ms: int
    status: RunStatus
    output: str | None = None
    error: str | None = None
    model: str | None = None
    usage_input_tokens: int | None = None
    usage_output_tokens: int | None = None
    usage_total_tokens: int | None = None
    trigger_source: str | None = None
    delivery_status: DeliveryStatus | None = None
    delivery_error: str | None = None
    metadata: dict[str, object] | None = None


@dataclass(frozen=True, slots=True)
class JobResult:
    """Return value from a job runner.

    ``metadata`` carries structured data collected during execution
    (e.g. progressSteps, sources) for delivery alongside the text output.

    ``exit_code`` follows Unix conventions:
    - 0: success, no new content (skip delivery)
    - 1: success, new content found (trigger delivery)
    - 2+: error (trigger failure delivery)

    ``incremental_delta`` contains only the new/changed content when
    incremental monitoring is enabled. Empty string means no changes.

    When ``skipped`` is True, the runner determined that execution
    should be bypassed (e.g. no actionable content for heartbeat).
    The executor records this as ``RunStatus.SKIPPED`` without
    running delivery or incrementing failure counters.

    ``retry_at`` is the earliest instant a repeat can succeed (e.g. the provider
    quota window reopens). The executor re-arms the job there, records the run as
    ``RunStatus.SKIPPED`` and counts no failure; it takes precedence over ``skipped``
    and, unlike it, keeps one-shot jobs alive.

    ``retry_safe`` is False when a repeat cannot help or could do harm: it could redo something
    the run already did (a tool that changes state was called, a workflow step began), spend the
    same time budget again, or meet the same cause of failure (a revoked key, a context that is
    too long, a gate that turned the job away). If such a run counts as failed, the executor
    leaves the job for its next regular slot instead of re-running it early, and the runner stops
    retrying in-process. Runners that cannot tell keep the default.
    """

    success: bool
    output: str = ""
    error: str | None = None
    metadata: dict[str, object] | None = None
    exit_code: int = 0
    incremental_delta: str = ""
    skipped: bool = False
    skip_reason: str | None = None
    circuit_broken: bool = False
    retry_at: datetime | None = None
    retry_safe: bool = True


class CronNoticeKind(StrEnum):
    """What a ``CronNotice`` reports.

    The engine states the fact; the application layer owns severity and wording, so a notice
    never carries presentation vocabulary of its own.
    """

    RUN_SUCCEEDED = "run_succeeded"
    RUN_FAILED = "run_failed"
    RUN_INTERRUPTED = "run_interrupted"
    JOB_EXPIRED = "job_expired"
    JOB_MAX_FIRES_REACHED = "job_max_fires_reached"
    JOB_PAUSED_BY_FAILURE = "job_paused_by_failure"


@dataclass(frozen=True, slots=True)
class CronNotice:
    """One user-facing fact about a job: a run's outcome, a run a crash cut short, or the scheduler pausing the job.

    ``job_name`` is the job's stored name, which the application presents as it sees fit. ``text`` is the bare
    output-or-error snippet of the run for ``RUN_SUCCEEDED`` and ``RUN_FAILED`` and empty for every other kind.
    ``chat_id`` is the chat the job is bound to, set on run outcomes (an interrupted run included) only.
    ``max_fires`` is the limit a ``JOB_MAX_FIRES_REACHED`` pause hit.
    """

    kind: CronNoticeKind
    job_name: str
    text: str = ""
    chat_id: str | None = None
    max_fires: int | None = None
