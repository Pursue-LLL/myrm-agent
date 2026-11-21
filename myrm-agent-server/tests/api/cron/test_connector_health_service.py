"""Connector health over real cron rows: which runs count as delivery attempts and what they say about a destination.

[INPUT]
- app.services.cron.connector_health_service::ConnectorHealthService, ConnectorHealthSummary (POS: the aggregation under test)
- app.core.cron.adapters.sqlalchemy_store::SqlAlchemyCronStore (POS: the SQL store the jobs and runs are written through)
- myrm_agent_harness.toolkits.cron.engine.executor::JobExecutor (POS: the writer of the run records the report reads)
- tests.support.policy_sqlite::policy_database (POS: a file SQLite database that runs the production transaction policy)

[OUTPUT]
- A run counts only if its delivery was attempted: skipped or absent deliveries add nothing and cannot crowd failed
  deliveries out of the rows the service reads
- A task's own failure does not make its connector unhealthy; only a failed delivery's error describes the destination
- Status follows the delivery streak: one failure degrades, three or an auth failure take the destination down, a
  delivery ends the streak
- Jobs group by destination (channel and exact address) whatever their status; in-app and addressless jobs have no
  connector, and two bots whose redacted addresses read alike stay apart
- A run counts for the destination it was delivered to, not for the one its job points at now
- The records the executor writes are the ones the report reads, for a failure that carries no text as well

[POS]
The service decides which rows it selects (statuses, window, how many) and which of their fields it believes. A mocked
session cannot show any of that, so every case runs against real rows.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock

import httpx
import pytest
from myrm_agent_harness.api import ConnectorErrorCategory, ConnectorHealthStatus, delivery_target_key
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
from app.services.cron.connector_health_service import ConnectorHealthService, ConnectorHealthSummary
from tests.support.policy_sqlite import policy_database

Attempt = tuple[DeliveryStatus, str | None]

_WEBHOOK = "https://hooks.example.com/notify?token=secret123"
_OK: Attempt = (DeliveryStatus.DELIVERED, None)
_BAD_GATEWAY: Attempt = (DeliveryStatus.FAILED, "Webhook returned 502: Bad Gateway")
_UNAUTHORIZED: Attempt = (DeliveryStatus.FAILED, "Webhook returned 401: Unauthorized")


@pytest.fixture
async def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[SqlAlchemyCronStore]:
    """A store on a test database that the service's ``UnitOfWork`` reads as well."""
    async with policy_database(tmp_path / "connector_health.db", monkeypatch) as db:
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
) -> datetime:
    """Store a run that started ``minutes_ago`` minutes ago and return when it finished.

    The run carries the key of the destination its job points at right now (unless ``stamped`` is off). Every run
    gets one, skipped ones too, so that only the delivery status keeps those out of the count.
    """
    job = await store.get_job(job_id)
    assert job is not None
    key = delivery_target_key(job.delivery.channel, job.delivery.target)
    started_at = datetime.now(UTC) - timedelta(minutes=minutes_ago)
    finished_at = started_at + timedelta(seconds=5)
    await store.save_run(
        CronRunRecord(
            id=f"{job_id}-{minutes_ago}",
            job_id=job_id,
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=5_000,
            status=task,
            delivery_status=delivery,
            delivery_error=error,
            metadata={"delivery_key": key} if key and stamped else None,
        )
    )
    return finished_at


async def _only_summary() -> ConnectorHealthSummary:
    [summary] = await ConnectorHealthService.get_all_connectors_health()
    return summary


async def test_a_failing_task_does_not_make_its_connector_unhealthy(store: SqlAlchemyCronStore) -> None:
    """The notice of a failed task reaches the target: the task's error and failure count describe the task, not the target."""
    await store.save_job(_job("report", _WEBHOOK, consecutive_failures=5, last_error="401 Unauthorized: invalid api key"))
    stored = await store.get_job("report")
    assert stored is not None
    assert stored.consecutive_failures == 5  # the task's failure state is really there to be ignored
    for minutes_ago in (5, 15):
        await _run(store, "report", minutes_ago, DeliveryStatus.DELIVERED, task=RunStatus.ERROR)

    summary = await _only_summary()

    assert summary.status == ConnectorHealthStatus.HEALTHY
    assert (summary.total_deliveries, summary.failed_deliveries, summary.consecutive_failures) == (2, 0, 0)
    assert summary.last_error_message is None
    assert summary.last_error_category is None


async def test_runs_without_a_delivery_attempt_are_not_counted(store: SqlAlchemyCronStore) -> None:
    """A skipped delivery and a run that never reached delivery are no attempts: neither counts, neither is the last delivery."""
    await store.save_job(_job("watch", _WEBHOOK))
    await _run(store, "watch", 1, DeliveryStatus.SKIPPED)
    await _run(store, "watch", 2, None)
    delivered_at = await _run(store, "watch", 30, DeliveryStatus.DELIVERED)

    summary = await _only_summary()

    assert summary.total_deliveries == 1
    assert summary.last_delivery_at is not None
    assert summary.last_delivery_at.replace(tzinfo=UTC) == delivered_at  # SQLite hands datetimes back without a zone


async def test_skipped_runs_cannot_crowd_failed_deliveries_out(store: SqlAlchemyCronStore) -> None:
    """A busy job that mostly skips delivery still shows the failures behind its skipped runs."""
    await store.save_job(_job("poll", _WEBHOOK))
    for minutes_ago in range(1, 52):  # newer than the failures, and more than the rows the service reads
        await _run(store, "poll", minutes_ago, DeliveryStatus.SKIPPED)
    for minutes_ago in (100, 101, 102):
        await _run(store, "poll", minutes_ago, *_BAD_GATEWAY)

    summary = await _only_summary()

    assert summary.status == ConnectorHealthStatus.DOWN
    assert (summary.total_deliveries, summary.failed_deliveries, summary.consecutive_failures) == (3, 3, 3)
    assert summary.last_error_category == ConnectorErrorCategory.HTTP_SERVER_ERROR


async def test_counts_cover_only_the_latest_attempts(store: SqlAlchemyCronStore) -> None:
    """A target with more attempts in the window than the service reads is judged by the latest ones."""
    await store.save_job(_job("busy", _WEBHOOK))
    for minutes_ago in range(1, 56):
        await _run(store, "busy", minutes_ago, *_OK)

    summary = await _only_summary()

    assert summary.total_deliveries == 50


@pytest.mark.parametrize(
    ("attempts", "status", "streak"),
    [
        pytest.param([_OK], ConnectorHealthStatus.HEALTHY, 0, id="delivered"),
        pytest.param([_BAD_GATEWAY, _OK], ConnectorHealthStatus.DEGRADED, 1, id="one-failure-after-a-delivery"),
        pytest.param([_BAD_GATEWAY, _BAD_GATEWAY, _OK], ConnectorHealthStatus.DEGRADED, 2, id="two-failures-after-a-delivery"),
        pytest.param([_OK, _BAD_GATEWAY, _BAD_GATEWAY, _BAD_GATEWAY], ConnectorHealthStatus.HEALTHY, 0, id="recovered"),
        pytest.param([_BAD_GATEWAY] * 3, ConnectorHealthStatus.DOWN, 3, id="three-failures"),
        pytest.param([_UNAUTHORIZED], ConnectorHealthStatus.DOWN, 1, id="auth-failure-alone"),
    ],
)
async def test_status_follows_the_delivery_streak(
    store: SqlAlchemyCronStore, attempts: list[Attempt], status: ConnectorHealthStatus, streak: int
) -> None:
    """``attempts`` run newest first; failures count until the first delivery."""
    await store.save_job(_job("job", _WEBHOOK))
    for minutes_ago, (delivery, error) in enumerate(attempts, start=1):
        await _run(store, "job", minutes_ago, delivery, error)

    summary = await _only_summary()

    assert (summary.status, summary.consecutive_failures) == (status, streak)


async def test_jobs_group_by_destination(store: SqlAlchemyCronStore) -> None:
    """Every job with an outbound address belongs to its destination, paused or not; the address shows no secret."""
    await store.save_job(_job("active", _WEBHOOK))
    await store.save_job(_job("paused", _WEBHOOK, status=JobStatus.PAUSED))  # its past attempts still describe the target
    await store.save_job(_job("feishu", _WEBHOOK, channel="feishu"))  # same address on another channel: its own connector
    await store.save_job(_job("no-address", None))  # nowhere to deliver
    await store.save_job(_job("in-app", _WEBHOOK, channel="chat"))  # the chat is not an outbound target
    await _run(store, "active", 10, *_OK)
    await _run(store, "paused", 5, *_BAD_GATEWAY)
    await _run(store, "feishu", 5, *_OK)

    summaries = await ConnectorHealthService.get_all_connectors_health()

    by_channel = {summary.channel: summary for summary in summaries}
    assert len(summaries) == 2
    assert set(by_channel) == {"webhook", "feishu"}
    webhook = by_channel["webhook"]
    assert "secret123" not in webhook.target
    assert sorted(webhook.bound_job_ids) == ["active", "paused"]
    assert (webhook.total_deliveries, webhook.failed_deliveries, webhook.consecutive_failures) == (2, 1, 1)
    assert webhook.status == ConnectorHealthStatus.DEGRADED
    assert by_channel["feishu"].bound_job_ids == ("feishu",)
    assert by_channel["feishu"].status == ConnectorHealthStatus.HEALTHY


async def test_bots_whose_redacted_addresses_read_alike_stay_apart(store: SqlAlchemyCronStore) -> None:
    """Redaction masks the key that tells two bots of one platform apart; a failing bot must not condemn the other."""
    bot_a = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=aaaa-1111"
    bot_b = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=bbbb-2222"
    await store.save_job(_job("bot-a", bot_a, channel="wecom"))
    await store.save_job(_job("bot-b", bot_b, channel="wecom"))
    for minutes_ago in (1, 2, 3):
        await _run(store, "bot-a", minutes_ago, *_BAD_GATEWAY)
    await _run(store, "bot-b", 1, *_OK)

    summaries = {summary.bound_job_ids: summary for summary in await ConnectorHealthService.get_all_connectors_health()}

    assert set(summaries) == {("bot-a",), ("bot-b",)}
    failing, healthy = summaries[("bot-a",)], summaries[("bot-b",)]
    assert failing.target == healthy.target  # the address shown cannot tell them apart
    assert failing.status == ConnectorHealthStatus.DOWN
    assert healthy.status == ConnectorHealthStatus.HEALTHY
    assert (healthy.total_deliveries, healthy.failed_deliveries) == (1, 0)


async def test_a_run_counts_for_the_destination_it_was_delivered_to(store: SqlAlchemyCronStore) -> None:
    """A job pointed somewhere else keeps its attempts at the earlier address out of the new address's health."""
    old, new = "https://hooks.example.com/old", "https://hooks.example.com/new"
    await store.save_job(_job("moved", old))
    for minutes_ago in (10, 11, 12):
        await _run(store, "moved", minutes_ago, *_BAD_GATEWAY)
    await store.save_job(_job("moved", new))
    await _run(store, "moved", 1, *_OK)

    summary = await _only_summary()

    assert summary.target == new
    assert summary.status == ConnectorHealthStatus.HEALTHY
    assert (summary.total_deliveries, summary.failed_deliveries) == (1, 0)


async def test_an_attempt_that_names_no_destination_is_not_counted(store: SqlAlchemyCronStore) -> None:
    """A run without a destination key cannot be told apart from another job's, so it is left out, not guessed at."""
    await store.save_job(_job("unkeyed", _WEBHOOK))
    await _run(store, "unkeyed", 1, *_BAD_GATEWAY, stamped=False)
    await _run(store, "unkeyed", 2, *_OK)

    summary = await _only_summary()

    assert summary.status == ConnectorHealthStatus.HEALTHY
    assert (summary.total_deliveries, summary.failed_deliveries) == (1, 0)


class _FailingDelivery:
    """A delivery that raises ``error`` for every address that contains ``bad`` and succeeds for the rest."""

    def __init__(self, error: Exception) -> None:
        self._error = error

    async def deliver(self, job: CronJob, result: JobResult) -> None:
        if "bad" in (job.delivery.target or ""):
            raise self._error


async def test_what_the_executor_records_is_what_the_report_reads(store: SqlAlchemyCronStore) -> None:
    """A delivery that times out carries no text: its run must still say why, and the report must classify it."""
    await store.save_job(_job("to-good", "https://hooks.example.com/good?token=g"))
    await store.save_job(_job("to-bad", "https://hooks.example.com/bad?token=b"))
    executor = JobExecutor(store=store, delivery=_FailingDelivery(httpx.ReadTimeout("")))
    runner = AsyncMock()
    runner.run = AsyncMock(return_value=JobResult(success=True, output="report"))

    for job_id in ("to-good", "to-bad", "to-bad", "to-bad"):
        job = await store.get_job(job_id)
        assert job is not None
        await executor.run_and_record(job, runner)

    summaries = {summary.bound_job_ids: summary for summary in await ConnectorHealthService.get_all_connectors_health()}

    bad = summaries[("to-bad",)]
    assert (bad.status, bad.consecutive_failures) == (ConnectorHealthStatus.DOWN, 3)
    assert bad.last_error_category == ConnectorErrorCategory.TIMEOUT
    assert bad.last_error_message == "ReadTimeout"
    assert summaries[("to-good",)].status == ConnectorHealthStatus.HEALTHY
