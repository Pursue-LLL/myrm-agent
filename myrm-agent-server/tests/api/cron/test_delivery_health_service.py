"""Delivery health over real cron rows: which runs count as delivery attempts and what they say about a destination.

[INPUT]
- app.services.cron.delivery_health_service::DeliveryHealth, DeliveryHealthService, DeliveryHealthStatus (POS: the judgment under test)
- app.core.cron.adapters.sqlalchemy_store::SqlAlchemyCronStore (POS: the SQL store the jobs and runs are written through)
- myrm_agent_harness.toolkits.cron.engine.executor::JobExecutor (POS: the writer of the run records the service reads)
- tests.support.policy_sqlite::policy_database (POS: a file SQLite database that runs the production transaction policy)

[OUTPUT]
- A run counts only if its delivery was attempted: skipped or absent deliveries add nothing and cannot crowd failed
  deliveries out of the rows the service reads
- A task's own failure does not make its destination unhealthy; only a failed delivery's error describes it
- Status follows the delivery streak: one failure degrades, three or a refusal that no retry fixes take the destination
  down, a delivery ends the streak
- Jobs group by destination (channel and exact address) whatever their status; in-app and addressless deliveries have
  no destination, and two bots whose redacted addresses read alike stay apart
- A run counts for the destination it was delivered to, not for the one its job points at now
- Attempts are read from the last day and ordered by when they finished, not by when they started
- The records the executor writes are the ones the service reads, for a failure that carries no text as well

[POS]
The service decides which rows it selects (statuses, window, order, how many) and which of their fields it believes. A
mocked session cannot show any of that, so every case runs against real rows.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock

import httpx
import pytest
from myrm_agent_harness.api import ConnectorErrorCategory, delivery_target_key, redact_connector_url
from myrm_agent_harness.toolkits.cron import (
    CronJob,
    CronRunRecord,
    DeliveryConfig,
    DeliveryStatus,
    JobResult,
    JobStatus,
    JobType,
    RunStatus,
    Schedule,
    ScheduleKind,
)
from myrm_agent_harness.toolkits.cron.engine.executor import JobExecutor

from app.core.cron.adapters.sqlalchemy_store import SqlAlchemyCronStore
from app.services.cron.delivery_health_service import DeliveryHealth, DeliveryHealthService, DeliveryHealthStatus
from tests.support.policy_sqlite import policy_database

Attempt = tuple[DeliveryStatus, str | None]

_WEBHOOK = "https://hooks.example.com/notify?token=secret123"
_OK: Attempt = (DeliveryStatus.DELIVERED, None)
_BAD_GATEWAY: Attempt = (DeliveryStatus.FAILED, "Webhook returned 502: Bad Gateway")
_UNAUTHORIZED: Attempt = (DeliveryStatus.FAILED, "Webhook returned 401: Unauthorized")
_REFUSED_ADDRESS: Attempt = (
    DeliveryStatus.FAILED,
    "Access to internal network is blocked for security reasons. Blocked IP: 10.0.0.5 is a non-public IP address",
)


@pytest.fixture
async def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[SqlAlchemyCronStore]:
    """A store on a test database that the service's ``UnitOfWork`` reads as well."""
    async with policy_database(tmp_path / "delivery_health.db", monkeypatch) as db:
        # ``UnitOfWork`` takes its factory from ``app.platform_utils``, which ``policy_database`` does not redirect
        monkeypatch.setattr("app.database.repositories.uow.get_session_factory", lambda: db.factory)
        yield SqlAlchemyCronStore()


def _job(
    job_id: str,
    target: str | None,
    *,
    channel: str = "webhook",
    status: JobStatus = JobStatus.ACTIVE,
    consecutive_failures: int = 0,
    last_error: str | None = None,
) -> CronJob:
    return CronJob(
        id=job_id,
        name=job_id,
        job_type=JobType.ROUTER,
        schedule=Schedule(kind=ScheduleKind.INTERVAL, interval_ms=3_600_000),
        command="__probe__",
        status=status,
        delivery=DeliveryConfig(channel=channel, target=target),
        last_status=RunStatus.ERROR if last_error else None,
        last_error=last_error,
        consecutive_failures=consecutive_failures,
    )


async def _run(
    store: SqlAlchemyCronStore,
    job_id: str,
    minutes_ago: int,
    delivery: DeliveryStatus | None,
    error: str | None = None,
    *,
    task: RunStatus = RunStatus.OK,
    stamped: bool = True,
    seconds_to_finish: int = 5,
) -> datetime:
    """Store a run that started ``minutes_ago`` minutes ago and return when it finished.

    The run carries the key of the destination its job points at right now (unless ``stamped`` is off). Every run
    gets one, skipped ones too, so that only the delivery status keeps those out of the count.
    """
    job = await store.get_job(job_id)
    assert job is not None
    key = delivery_target_key(job.delivery.channel, job.delivery.target)
    started_at = datetime.now(UTC) - timedelta(minutes=minutes_ago)
    finished_at = started_at + timedelta(seconds=seconds_to_finish)
    await store.save_run(
        CronRunRecord(
            id=f"{job_id}-{minutes_ago}",
            job_id=job_id,
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=seconds_to_finish * 1_000,
            status=task,
            delivery_status=delivery,
            delivery_error=error,
            metadata={"delivery_key": key} if key and stamped else None,
        )
    )
    return finished_at


async def _verdict(channel: str = "webhook", target: str | None = _WEBHOOK) -> DeliveryHealth:
    health = await DeliveryHealthService.get_destination_health(channel, target)
    assert health is not None, f"{channel} {target} should have a verdict"
    return health


async def test_a_failing_task_does_not_make_its_destination_unhealthy(store: SqlAlchemyCronStore) -> None:
    """The notice of a failed task reaches the target: the task's error and failure count describe the task, not the target."""
    await store.save_job(_job("report", _WEBHOOK, consecutive_failures=5, last_error="401 Unauthorized: invalid api key"))
    stored = await store.get_job("report")
    assert stored is not None
    assert stored.consecutive_failures == 5  # the task's failure state is really there to be ignored
    for minutes_ago in (5, 15):
        await _run(store, "report", minutes_ago, DeliveryStatus.DELIVERED, task=RunStatus.ERROR)

    assert await _verdict() == DeliveryHealth(DeliveryHealthStatus.HEALTHY, failure_streak=0)


async def test_a_destination_nothing_was_delivered_to_has_no_verdict(store: SqlAlchemyCronStore) -> None:
    """A skipped delivery and a run that never reached delivery are no attempts, so there is nothing to judge."""
    await store.save_job(_job("watch", _WEBHOOK))
    await _run(store, "watch", 1, DeliveryStatus.SKIPPED)
    await _run(store, "watch", 2, None)

    assert await DeliveryHealthService.get_destination_health("webhook", _WEBHOOK) is None


async def test_skipped_runs_cannot_crowd_failed_deliveries_out(store: SqlAlchemyCronStore) -> None:
    """A busy job that mostly skips delivery still shows the failures behind its skipped runs."""
    await store.save_job(_job("poll", _WEBHOOK))
    for minutes_ago in range(1, 52):  # newer than the failures, and more than the rows the service reads
        await _run(store, "poll", minutes_ago, DeliveryStatus.SKIPPED)
    for minutes_ago in (100, 101, 102):
        await _run(store, "poll", minutes_ago, *_BAD_GATEWAY)

    health = await _verdict()

    assert (health.status, health.failure_streak) == (DeliveryHealthStatus.DOWN, 3)
    assert health.last_error_category == ConnectorErrorCategory.HTTP_SERVER_ERROR


async def test_only_the_latest_attempts_are_read(store: SqlAlchemyCronStore) -> None:
    """A destination with more attempts in the window than the service reads is judged by the latest ones."""
    await store.save_job(_job("busy", _WEBHOOK))
    for minutes_ago in range(1, 56):
        await _run(store, "busy", minutes_ago, *_BAD_GATEWAY)

    assert (await _verdict()).failure_streak == 50


@pytest.mark.parametrize(
    ("attempts", "status", "streak"),
    [
        pytest.param([_OK], DeliveryHealthStatus.HEALTHY, 0, id="delivered"),
        pytest.param([_BAD_GATEWAY, _OK], DeliveryHealthStatus.DEGRADED, 1, id="one-failure-after-a-delivery"),
        pytest.param([_BAD_GATEWAY, _BAD_GATEWAY, _OK], DeliveryHealthStatus.DEGRADED, 2, id="two-failures-after-a-delivery"),
        pytest.param([_OK, _BAD_GATEWAY, _BAD_GATEWAY, _BAD_GATEWAY], DeliveryHealthStatus.HEALTHY, 0, id="recovered"),
        pytest.param([_BAD_GATEWAY] * 3, DeliveryHealthStatus.DOWN, 3, id="three-failures"),
        pytest.param([_UNAUTHORIZED], DeliveryHealthStatus.DOWN, 1, id="rejected-credentials-alone"),
        pytest.param([_REFUSED_ADDRESS], DeliveryHealthStatus.DOWN, 1, id="refused-address-alone"),
        pytest.param([_REFUSED_ADDRESS, _OK], DeliveryHealthStatus.DOWN, 1, id="refused-address-after-a-delivery"),
        pytest.param([_OK, _REFUSED_ADDRESS], DeliveryHealthStatus.HEALTHY, 0, id="refused-address-then-delivered"),
    ],
)
async def test_status_follows_the_delivery_streak(
    store: SqlAlchemyCronStore, attempts: list[Attempt], status: DeliveryHealthStatus, streak: int
) -> None:
    """``attempts`` run newest first; failures count until the first delivery."""
    await store.save_job(_job("job", _WEBHOOK))
    for minutes_ago, (delivery, error) in enumerate(attempts, start=1):
        await _run(store, "job", minutes_ago, delivery, error)

    health = await _verdict()

    assert (health.status, health.failure_streak) == (status, streak)


async def test_the_failure_fields_describe_the_newest_failure(store: SqlAlchemyCronStore) -> None:
    await store.save_job(_job("job", _WEBHOOK))
    failed_at = await _run(store, "job", 3, *_REFUSED_ADDRESS)
    await _run(store, "job", 30, *_BAD_GATEWAY)

    health = await _verdict()

    assert health.last_error_category == ConnectorErrorCategory.ADDRESS_REJECTED
    # SQLite hands datetimes back without a zone; the service names the moment, so a client cannot read it as local time
    assert health.last_failed_at == failed_at


async def test_a_healthy_destination_reports_no_failure(store: SqlAlchemyCronStore) -> None:
    await store.save_job(_job("job", _WEBHOOK))
    await _run(store, "job", 1, *_OK)
    await _run(store, "job", 2, *_BAD_GATEWAY)

    health = await _verdict()

    assert (health.last_error_category, health.last_failed_at) == (None, None)


async def test_a_failure_without_error_text_is_an_unknown_failure(store: SqlAlchemyCronStore) -> None:
    await store.save_job(_job("job", _WEBHOOK))
    await _run(store, "job", 1, DeliveryStatus.FAILED, None)

    health = await _verdict()

    assert (health.status, health.last_error_category) == (DeliveryHealthStatus.DEGRADED, ConnectorErrorCategory.UNKNOWN)


async def test_jobs_group_by_destination(store: SqlAlchemyCronStore) -> None:
    """Every job with an outbound address belongs to its destination, paused or not."""
    await store.save_job(_job("active", _WEBHOOK))
    await store.save_job(_job("paused", _WEBHOOK, status=JobStatus.PAUSED))  # its past attempts still describe the target
    await store.save_job(_job("feishu", _WEBHOOK, channel="feishu"))  # same address on another channel: its own destination
    await store.save_job(_job("in-app", _WEBHOOK, channel="chat"))  # the chat is not an outbound target
    await _run(store, "active", 10, *_OK)
    await _run(store, "paused", 5, *_BAD_GATEWAY)
    await _run(store, "feishu", 5, *_OK)

    webhook = await _verdict("webhook", _WEBHOOK)
    assert (webhook.status, webhook.failure_streak) == (DeliveryHealthStatus.DEGRADED, 1)
    assert (await _verdict("feishu", _WEBHOOK)).status == DeliveryHealthStatus.HEALTHY


@pytest.mark.parametrize(
    ("channel", "target"),
    [("webhook", None), ("webhook", "   "), ("chat", _WEBHOOK), ("silent", _WEBHOOK), ("none", _WEBHOOK)],
    ids=["no-address", "blank-address", "chat", "silent", "none"],
)
async def test_a_delivery_that_leaves_nothing_outside_has_no_destination(
    store: SqlAlchemyCronStore, channel: str, target: str | None
) -> None:
    await store.save_job(_job("job", target, channel=channel))
    await _run(store, "job", 1, *_BAD_GATEWAY)

    assert await DeliveryHealthService.get_destination_health(channel, target) is None


async def test_bots_whose_redacted_addresses_read_alike_stay_apart(store: SqlAlchemyCronStore) -> None:
    """Redaction masks the key that tells two bots of one platform apart; a failing bot must not condemn the other."""
    bot_a = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=aaaa-1111"
    bot_b = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=bbbb-2222"
    assert redact_connector_url(bot_a) == redact_connector_url(bot_b)  # the address shown cannot tell them apart
    await store.save_job(_job("bot-a", bot_a, channel="wecom"))
    await store.save_job(_job("bot-b", bot_b, channel="wecom"))
    for minutes_ago in (1, 2, 3):
        await _run(store, "bot-a", minutes_ago, *_BAD_GATEWAY)
    await _run(store, "bot-b", 1, *_OK)

    assert (await _verdict("wecom", bot_a)).status == DeliveryHealthStatus.DOWN
    assert await _verdict("wecom", bot_b) == DeliveryHealth(DeliveryHealthStatus.HEALTHY, failure_streak=0)


async def test_a_run_counts_for_the_destination_it_was_delivered_to(store: SqlAlchemyCronStore) -> None:
    """A job pointed somewhere else keeps its attempts at the earlier address out of the new address's health."""
    old, new = "https://hooks.example.com/old", "https://hooks.example.com/new"
    await store.save_job(_job("moved", old))
    for minutes_ago in (10, 11, 12):
        await _run(store, "moved", minutes_ago, *_BAD_GATEWAY)
    await store.save_job(_job("moved", new))
    await _run(store, "moved", 1, *_OK)

    assert await _verdict("webhook", new) == DeliveryHealth(DeliveryHealthStatus.HEALTHY, failure_streak=0)
    assert await DeliveryHealthService.get_destination_health("webhook", old) is None  # no job delivers there now


async def test_an_attempt_that_names_no_destination_is_not_counted(store: SqlAlchemyCronStore) -> None:
    """A run without a destination key cannot be told apart from another job's, so it is left out, not guessed at."""
    await store.save_job(_job("unkeyed", _WEBHOOK))
    await _run(store, "unkeyed", 1, *_BAD_GATEWAY, stamped=False)
    await _run(store, "unkeyed", 2, *_OK)

    assert (await _verdict()).status == DeliveryHealthStatus.HEALTHY


async def test_the_run_that_delivered_last_decides_not_the_one_that_started_last(store: SqlAlchemyCronStore) -> None:
    """Runs overlap: a slow one that started first and delivered last is the destination's latest word."""
    await store.save_job(_job("slow", _WEBHOOK))
    await store.save_job(_job("quick", _WEBHOOK))
    await _run(store, "slow", 40, *_OK, seconds_to_finish=29 * 60)  # started first, delivered 11 minutes ago
    await _run(store, "quick", 20, *_BAD_GATEWAY)  # started later, failed 20 minutes ago

    assert await _verdict() == DeliveryHealth(DeliveryHealthStatus.HEALTHY, failure_streak=0)


async def test_attempts_older_than_a_day_have_no_say(store: SqlAlchemyCronStore) -> None:
    await store.save_job(_job("old", _WEBHOOK))
    for minutes_ago in (25 * 60, 26 * 60, 27 * 60):
        await _run(store, "old", minutes_ago, *_BAD_GATEWAY)

    assert await DeliveryHealthService.get_destination_health("webhook", _WEBHOOK) is None


async def test_the_window_counts_from_when_the_run_finished(store: SqlAlchemyCronStore) -> None:
    """A long run that started just outside the day but delivered inside it is an attempt of the last day."""
    await store.save_job(_job("long", _WEBHOOK))
    await _run(store, "long", 24 * 60 + 10, *_BAD_GATEWAY, seconds_to_finish=20 * 60)

    assert (await _verdict()).failure_streak == 1


class _FailingDelivery:
    """A delivery that raises ``error`` for every address that contains ``bad`` and succeeds for the rest."""

    def __init__(self, error: Exception) -> None:
        self._error = error

    async def deliver(self, job: CronJob, result: JobResult) -> None:
        if "bad" in (job.delivery.target or ""):
            raise self._error


async def test_what_the_executor_records_is_what_the_service_reads(store: SqlAlchemyCronStore) -> None:
    """A delivery that times out carries no text: its run must still say why, and the service must classify it."""
    good, bad = "https://hooks.example.com/good?token=g", "https://hooks.example.com/bad?token=b"
    await store.save_job(_job("to-good", good))
    await store.save_job(_job("to-bad", bad))
    executor = JobExecutor(store=store, delivery=_FailingDelivery(httpx.ReadTimeout("")))
    runner = AsyncMock()
    runner.run = AsyncMock(return_value=JobResult(success=True, output="report"))

    for job_id in ("to-good", "to-bad", "to-bad", "to-bad"):
        job = await store.get_job(job_id)
        assert job is not None
        await executor.run_and_record(job, runner)

    health = await _verdict("webhook", bad)
    assert (health.status, health.failure_streak) == (DeliveryHealthStatus.DOWN, 3)
    assert health.last_error_category == ConnectorErrorCategory.TIMEOUT
    assert (await _verdict("webhook", good)).status == DeliveryHealthStatus.HEALTHY
