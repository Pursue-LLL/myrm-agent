"""Unit tests for engine/helpers.py — covers functions not tested elsewhere."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

import pytest

from myrm_agent_harness.toolkits.cron.engine import helpers
from myrm_agent_harness.toolkits.cron.engine.helpers import (
    BACKOFF_SCHEDULE_MS,
    _ensure_utc,
    classify_transient_error,
    error_backoff_ms,
    extract_telemetry,
    is_past_misfire_grace,
    next_slot_or_retry,
    pause_job,
    pre_execution_check,
    resolve_failure_alert,
    resolve_stagger_ms,
    should_send_failure_alert,
)
from myrm_agent_harness.toolkits.cron.types import (
    CronJob,
    DeliveryConfig,
    FailureAlertConfig,
    JobResult,
    JobStatus,
    JobType,
    PauseReason,
    Schedule,
    ScheduleKind,
)

_NOW = datetime(2026, 3, 29, 12, 0, 0, tzinfo=UTC)
_SCHED_CRON = Schedule(kind=ScheduleKind.CRON, expr="0 * * * *")
_SCHED_INTERVAL = Schedule(kind=ScheduleKind.INTERVAL, interval_ms=60_000)
_DELIVERY = DeliveryConfig(channel="none")


def _job(**overrides: object) -> CronJob:
    defaults: dict[str, object] = {
        "id": "j1",
        "name": "test",
        "job_type": JobType.SHELL,
        "command": "echo hi",
        "schedule": _SCHED_CRON,
        "delivery": _DELIVERY,
        "created_at": _NOW,
        "updated_at": _NOW,
    }
    defaults.update(overrides)
    return CronJob(**defaults)  # type: ignore[arg-type]


class TestEnsureUtc:
    def test_naive_gets_utc(self) -> None:
        naive = datetime(2026, 1, 1, 12, 0, 0)
        result = _ensure_utc(naive)
        assert result.tzinfo is UTC

    def test_aware_unchanged(self) -> None:
        aware = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
        assert _ensure_utc(aware) is aware


class TestStagger:
    def test_explicit_zero(self) -> None:
        sched = Schedule(kind=ScheduleKind.CRON, expr="0 * * * *", stagger_ms=0)
        assert resolve_stagger_ms(_job(schedule=sched)) == 0

    def test_explicit_value(self) -> None:
        sched = Schedule(kind=ScheduleKind.CRON, expr="0 * * * *", stagger_ms=10_000)
        assert resolve_stagger_ms(_job(schedule=sched)) == 10_000

    def test_auto_top_of_hour(self) -> None:
        assert resolve_stagger_ms(_job(schedule=_SCHED_CRON)) == 5 * 60 * 1000

    def test_auto_non_top_of_hour(self) -> None:
        sched = Schedule(kind=ScheduleKind.CRON, expr="30 * * * *")
        assert resolve_stagger_ms(_job(schedule=sched)) == 0

    def test_interval_no_stagger(self) -> None:
        assert resolve_stagger_ms(_job(schedule=_SCHED_INTERVAL)) == 0


class TestPreExecutionCheck:
    def test_expired(self) -> None:
        job = _job(expires_at=_NOW - timedelta(hours=1))
        assert pre_execution_check(job, _NOW) == "expired"
        assert job.status == JobStatus.PAUSED

    def test_max_fires_reached(self) -> None:
        job = _job(max_fires=5, fire_count=5)
        assert pre_execution_check(job, _NOW) == "max_fires_reached"

    def test_cooldown_active(self) -> None:
        job = _job(
            cooldown_seconds=300,
            last_run_at=_NOW - timedelta(seconds=60),
        )
        assert pre_execution_check(job, _NOW) == "cooldown_active"

    def test_runnable(self) -> None:
        assert pre_execution_check(_job(), _NOW) is None


class TestPauseJob:
    def test_an_active_job_is_paused_unbooked_and_carries_the_reason(self) -> None:
        job = _job(next_run_at=_NOW + timedelta(hours=1))

        pause_job(job, PauseReason.CIRCUIT_BREAK)

        assert (job.status, job.next_run_at, job.paused_reason) == (JobStatus.PAUSED, None, PauseReason.CIRCUIT_BREAK)

    def test_a_job_a_person_paused_stays_without_a_reason(self) -> None:
        job = _job(status=JobStatus.PAUSED, next_run_at=_NOW + timedelta(hours=1))

        pause_job(job, PauseReason.RUN_FAILURES)

        assert (job.status, job.next_run_at, job.paused_reason) == (JobStatus.PAUSED, None, None)

    def test_a_job_the_scheduler_already_paused_keeps_its_first_reason(self) -> None:
        job = _job(status=JobStatus.PAUSED, paused_reason=PauseReason.SCHEDULE_ERROR)

        pause_job(job, PauseReason.RUN_FAILURES)

        assert job.paused_reason == PauseReason.SCHEDULE_ERROR


class TestIsPastMisfireGrace:
    def test_past_grace(self) -> None:
        job = _job(
            next_run_at=_NOW - timedelta(minutes=30),
            misfire_grace_seconds=60,
        )
        assert is_past_misfire_grace(job, _NOW) is True

    def test_within_grace(self) -> None:
        job = _job(
            next_run_at=_NOW - timedelta(seconds=30),
            misfire_grace_seconds=60,
        )
        assert is_past_misfire_grace(job, _NOW) is False

    def test_no_next_run(self) -> None:
        job = _job(next_run_at=None)
        assert is_past_misfire_grace(job, _NOW) is False


class TestFailureAlert:
    def test_disabled_by_false(self) -> None:
        job = _job(failure_alert=False)
        assert resolve_failure_alert(job, None) is None

    def test_per_job_config(self) -> None:
        cfg = FailureAlertConfig(enabled=True, after=2, cooldown_seconds=60)
        job = _job(failure_alert=cfg)
        result = resolve_failure_alert(job, None)
        assert result is not None
        assert result.after == 2

    def test_global_fallback(self) -> None:
        global_cfg = FailureAlertConfig(enabled=True, after=3, cooldown_seconds=120)
        job = _job()
        result = resolve_failure_alert(job, global_cfg)
        assert result is not None
        assert result.after == 3

    def test_should_send_below_threshold(self) -> None:
        cfg = FailureAlertConfig(enabled=True, after=3, cooldown_seconds=60)
        job = _job(consecutive_failures=2)
        assert should_send_failure_alert(job, cfg, _NOW) is False

    def test_should_send_above_threshold(self) -> None:
        cfg = FailureAlertConfig(enabled=True, after=3, cooldown_seconds=60)
        job = _job(consecutive_failures=3)
        assert should_send_failure_alert(job, cfg, _NOW) is True

    def test_cooldown_prevents_send(self) -> None:
        cfg = FailureAlertConfig(enabled=True, after=1, cooldown_seconds=300)
        job = _job(
            consecutive_failures=5,
            last_failure_alert_at=_NOW - timedelta(seconds=60),
        )
        assert should_send_failure_alert(job, cfg, _NOW) is False

    def test_immediate_alert_skips_the_failure_threshold(self) -> None:
        cfg = FailureAlertConfig(enabled=True, after=3, cooldown_seconds=60)
        job = _job(consecutive_failures=1)
        assert should_send_failure_alert(job, cfg, _NOW, immediate=True) is True

    def test_immediate_alert_still_honours_the_cooldown(self) -> None:
        cfg = FailureAlertConfig(enabled=True, after=3, cooldown_seconds=300)
        job = _job(consecutive_failures=1, last_failure_alert_at=_NOW - timedelta(seconds=60))
        assert should_send_failure_alert(job, cfg, _NOW, immediate=True) is False


class TestErrorClassification:
    @pytest.mark.parametrize(
        "text,expected",
        [
            ("rate_limit exceeded", "rate_limit"),
            ("429 Too Many Requests", "rate_limit"),
            ("server overloaded", "overloaded"),
            ("connection refused", "network"),
            ("request timed out", "timeout"),
            ("500 Internal Server Error", "server_error"),
        ],
    )
    def test_transient_patterns(self, text: str, expected: str) -> None:
        result = classify_transient_error(text)
        assert result is not None
        assert result.value == expected

    def test_permanent_error(self) -> None:
        assert classify_transient_error("invalid syntax") is None


class TestErrorBackoff:
    def test_first_error(self) -> None:
        assert error_backoff_ms(1) == BACKOFF_SCHEDULE_MS[0]

    def test_max_cap(self) -> None:
        assert error_backoff_ms(100) == BACKOFF_SCHEDULE_MS[-1]

    def test_zero_errors(self) -> None:
        assert error_backoff_ms(0) == BACKOFF_SCHEDULE_MS[0]


class TestExtractTelemetry:
    def test_with_usage(self) -> None:
        result = JobResult(
            success=True,
            output="ok",
            metadata={
                "model": "gpt-4",
                "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
            },
        )
        model, p, c, t = extract_telemetry(result)
        assert model == "gpt-4"
        assert p == 10
        assert c == 20
        assert t == 30

    def test_no_metadata(self) -> None:
        result = JobResult(success=True, output="ok")
        assert extract_telemetry(result) == (None, None, None, None)

    def test_no_usage(self) -> None:
        result = JobResult(success=True, output="ok", metadata={"model": "gpt-4"})
        model, p, _c, _t = extract_telemetry(result)
        assert model == "gpt-4"
        assert p is None


class TestNextSlotOrRetry:
    def test_a_computable_schedule_is_booked_at_its_next_slot(self) -> None:
        assert next_slot_or_retry(_job(), _NOW) == _NOW + timedelta(hours=1)

    @pytest.mark.parametrize(
        "schedule",
        [
            Schedule(kind=ScheduleKind.CRON, expr="not a cron"),
            Schedule(kind=ScheduleKind.CRON, expr="0 0 31 2 *"),
            Schedule(kind=ScheduleKind.CRON, expr="0 * * * *", tz="Mars/Olympus"),
        ],
        ids=["unparseable", "no such date", "unknown timezone"],
    )
    def test_a_schedule_that_cannot_be_computed_is_booked_a_minute_ahead_with_a_warning(
        self, schedule: Schedule, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.WARNING):
            slot = next_slot_or_retry(_job(schedule=schedule), _NOW)

        assert slot == _NOW + timedelta(minutes=1)
        assert [record.levelno for record in caplog.records] == [logging.WARNING]
        assert "j1" in caplog.records[0].getMessage()

    def test_a_schedule_without_a_further_slot_is_still_booked_a_minute_ahead(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(helpers, "next_eligible_run", lambda job, now: None)

        assert next_slot_or_retry(_job(), _NOW) == _NOW + timedelta(minutes=1)
