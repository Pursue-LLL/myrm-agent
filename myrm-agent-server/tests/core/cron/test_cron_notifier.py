"""``publish_cron_notice`` turns the cron engine's notices into the events the WebUI, voice and push channels read.

The engine states facts only; the notifier owns severity, wording and language. The later tests run the real
scheduler so a run outcome, an automatic pause and a run a crash cut short each reach the event bus, and show that
the bus keeps them for a client that connects afterwards.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from myrm_agent_harness.toolkits.cron import HEARTBEAT_JOB_NAME, CronConfig, CronNotice, CronNoticeKind, CronScheduler
from myrm_agent_harness.toolkits.cron.stores import InMemoryCronStore
from myrm_agent_harness.toolkits.cron.types import (
    CronJob,
    JobResult,
    JobStatus,
    JobType,
    PauseReason,
    Schedule,
    ScheduleKind,
)

from app.core.cron.notifier import publish_cron_notice
from app.services.event.app_event_bus import AppEvent, AppEventType, ServerEventBus

_JOB = "Water the plants"


class _RecordingBus:
    def __init__(self) -> None:
        self.events: list[AppEvent] = []

    def publish(self, event: AppEvent) -> None:
        self.events.append(event)

    def notifications(self) -> list[AppEvent]:
        return [e for e in self.events if e.event_type == AppEventType.SYSTEM_NOTIFICATION]


@pytest.fixture
def bus(monkeypatch: pytest.MonkeyPatch) -> _RecordingBus:
    recorder = _RecordingBus()
    monkeypatch.setattr("app.core.cron.notifier.get_event_bus", lambda: recorder)
    return recorder


def _speak(monkeypatch: pytest.MonkeyPatch, locale: str) -> None:
    monkeypatch.setattr("app.core.cron.notifier.resolve_user_locale", AsyncMock(return_value=locale))


@pytest.fixture(autouse=True)
def _english(monkeypatch: pytest.MonkeyPatch) -> None:
    _speak(monkeypatch, "en")


@pytest.mark.parametrize(
    ("notice", "level", "event_kind", "title", "message"),
    [
        (
            CronNotice(CronNoticeKind.RUN_SUCCEEDED, _JOB, "all watered", "chat-1"),
            "success",
            "voice_background_task_done",
            f"Reminder: {_JOB}",
            f"[{_JOB}] all watered",
        ),
        (
            CronNotice(CronNoticeKind.RUN_FAILED, _JOB, "pump is dry", "chat-1"),
            "error",
            "voice_background_task_done",
            f"Scheduled task failed: {_JOB}",
            f"[{_JOB}] pump is dry",
        ),
        (
            CronNotice(CronNoticeKind.RUN_INTERRUPTED, _JOB, chat_id="chat-1"),
            "warning",
            "voice_background_task_done",
            f"Scheduled task interrupted: {_JOB}",
            "The app stopped while it was running, so this run did not finish.",
        ),
        (
            CronNotice(CronNoticeKind.JOB_EXPIRED, _JOB, chat_id="chat-1"),
            "warning",
            "cron_job_paused",
            f"Scheduled task paused: {_JOB}",
            "It reached its end time, so it was paused automatically.",
        ),
        (
            CronNotice(CronNoticeKind.JOB_MAX_FIRES_REACHED, _JOB, chat_id="chat-1", max_fires=3),
            "warning",
            "cron_job_paused",
            f"Scheduled task paused: {_JOB}",
            "It has run 3 times, which is its limit, so it was paused automatically.",
        ),
        (
            CronNotice(CronNoticeKind.JOB_PAUSED_BY_FAILURE, _JOB, chat_id="chat-1"),
            "warning",
            "cron_job_paused",
            f"Scheduled task paused: {_JOB}",
            "It hit a problem it could not recover from, so it was paused automatically. Open its Run History to see why, then resume it.",
        ),
    ],
    ids=["succeeded", "failed", "interrupted", "expired", "max-fires", "paused-by-failure"],
)
async def test_each_notice_kind_reads_as_its_severity_title_and_message(
    bus: _RecordingBus, notice: CronNotice, level: str, event_kind: str, title: str, message: str
) -> None:
    await publish_cron_notice(notice)

    (notification,) = bus.notifications()
    assert notification.data == {
        "title": title,
        "message": message,
        "meta_data": {"kind": event_kind, "level": level, "chat_id": "chat-1", "source": "cron_reminder"},
    }


async def test_cron_views_are_told_to_refresh_before_the_user_is_notified(bus: _RecordingBus) -> None:
    await publish_cron_notice(CronNotice(CronNoticeKind.RUN_FAILED, _JOB, "x", "chat-1"))

    assert [e.event_type for e in bus.events] == [AppEventType.CRON_UPDATED, AppEventType.SYSTEM_NOTIFICATION]
    assert bus.events[0].data == {
        "kind": "run_failed",
        "level": "error",
        "job_name": _JOB,
        "chat_id": "chat-1",
    }


async def test_a_job_without_a_chat_publishes_an_empty_chat_id(bus: _RecordingBus) -> None:
    await publish_cron_notice(CronNotice(CronNoticeKind.RUN_SUCCEEDED, _JOB, "x"))

    assert bus.notifications()[0].data["meta_data"]["chat_id"] == ""


@pytest.mark.parametrize(
    ("locale", "title", "interrupted_title", "pause_title", "max_fires_message", "failure_message", "interrupted_message"),
    [
        (
            "en",
            f"Reminder: {_JOB}",
            f"Scheduled task interrupted: {_JOB}",
            f"Scheduled task paused: {_JOB}",
            "It has run 3 times",
            "could not recover from",
            "did not finish",
        ),
        (
            "zh-CN",
            f"提醒：{_JOB}",
            f"定时任务被中断：{_JOB}",
            f"定时任务已暂停：{_JOB}",
            "已执行 3 次",
            "无法自行恢复",
            "没有完成",
        ),
    ],
)
async def test_titles_and_messages_speak_the_users_language(
    bus: _RecordingBus,
    monkeypatch: pytest.MonkeyPatch,
    locale: str,
    title: str,
    interrupted_title: str,
    pause_title: str,
    max_fires_message: str,
    failure_message: str,
    interrupted_message: str,
) -> None:
    _speak(monkeypatch, locale)

    await publish_cron_notice(CronNotice(CronNoticeKind.RUN_SUCCEEDED, _JOB, "x"))
    await publish_cron_notice(CronNotice(CronNoticeKind.RUN_INTERRUPTED, _JOB))
    await publish_cron_notice(CronNotice(CronNoticeKind.JOB_MAX_FIRES_REACHED, _JOB, max_fires=3))
    await publish_cron_notice(CronNotice(CronNoticeKind.JOB_PAUSED_BY_FAILURE, _JOB))

    run, interrupted, pause, failure_pause = (e.data for e in bus.notifications())
    assert run["title"] == title
    assert interrupted["title"] == interrupted_title
    assert interrupted_message in interrupted["message"]
    assert pause["title"] == pause_title
    assert max_fires_message in pause["message"]
    assert failure_pause["title"] == pause_title
    assert failure_message in failure_pause["message"]


@pytest.mark.parametrize(("locale", "name"), [("en", "Agent Auto-Check"), ("zh-CN", "Agent 自动巡检")])
async def test_a_system_job_goes_by_its_catalog_name_not_its_stored_one(
    bus: _RecordingBus, monkeypatch: pytest.MonkeyPatch, locale: str, name: str
) -> None:
    _speak(monkeypatch, locale)

    await publish_cron_notice(CronNotice(CronNoticeKind.RUN_SUCCEEDED, HEARTBEAT_JOB_NAME, "all quiet", "chat-1"))
    await publish_cron_notice(CronNotice(CronNoticeKind.JOB_PAUSED_BY_FAILURE, HEARTBEAT_JOB_NAME))

    run, pause = (e.data for e in bus.notifications())
    assert name in run["title"] and run["message"] == f"[{name}] all quiet"
    assert name in pause["title"]
    assert HEARTBEAT_JOB_NAME not in f"{run} {pause}"
    # The refresh event only wakes the views, which read the job itself.
    assert bus.events[0].data["job_name"] == HEARTBEAT_JOB_NAME


@pytest.mark.parametrize("locale", ["en", "zh-CN"])
@pytest.mark.parametrize("kind", list(CronNoticeKind))
async def test_every_notice_kind_reads_in_every_language(
    bus: _RecordingBus, monkeypatch: pytest.MonkeyPatch, kind: CronNoticeKind, locale: str
) -> None:
    """A kind without wording raises inside the scheduler's notice isolation and its notice vanishes; a catalog key
    that does not resolve reaches the user as the raw key."""
    _speak(monkeypatch, locale)

    await publish_cron_notice(CronNotice(kind, _JOB, "what the run said", "chat-1", max_fires=3))

    (notification,) = bus.notifications()
    for field in ("title", "message"):
        text = notification.data[field]
        assert text
        assert "cron_notice_" not in text


class _Delivery:
    async def deliver(self, job: CronJob, result: JobResult) -> None:
        return None


class _Runner:
    def __init__(self) -> None:
        self.result = JobResult(success=True, output="all watered")

    async def run(self, job: CronJob, *, context: str = "") -> JobResult:
        return self.result


async def _fire(job: CronJob, runner: _Runner) -> CronJob:
    """What the timer does for a booked due job, with the scheduler wired exactly as production wires it."""
    store = InMemoryCronStore()
    scheduler = CronScheduler(store, {JobType.AGENT: runner}, _Delivery(), config=CronConfig(), on_notice=publish_cron_notice)
    await store.save_job(job)
    snapshot = await store.get_job(job.id)
    assert snapshot is not None
    await scheduler._dispatch(snapshot)
    stored = await store.get_job(job.id)
    assert stored is not None
    return stored


_EVERY_HOUR = Schedule(kind=ScheduleKind.INTERVAL, interval_ms=3_600_000, stagger_ms=0)


def _job(
    *,
    schedule: Schedule = _EVERY_HOUR,
    expires_at: datetime | None = None,
    max_fires: int | None = None,
    fire_count: int = 0,
    consecutive_failures: int = 0,
) -> CronJob:
    return CronJob(
        id="job-1",
        name=_JOB,
        job_type=JobType.AGENT,
        schedule=schedule,
        prompt="prompt",
        chat_id="chat-9",
        expires_at=expires_at,
        max_fires=max_fires,
        fire_count=fire_count,
        consecutive_failures=consecutive_failures,
    )


@pytest.mark.parametrize(
    ("result", "level", "title"),
    [
        (JobResult(success=True, output="all watered"), "success", f"Reminder: {_JOB}"),
        (JobResult(success=False, error="pump is dry"), "error", f"Scheduled task failed: {_JOB}"),
    ],
    ids=["succeeded", "failed"],
)
async def test_a_scheduled_run_notifies_the_chat_it_is_bound_to(
    bus: _RecordingBus, result: JobResult, level: str, title: str
) -> None:
    runner = _Runner()
    runner.result = result

    await _fire(_job(), runner)

    (notification,) = bus.notifications()
    assert notification.data["title"] == title
    assert notification.data["meta_data"]["level"] == level
    assert notification.data["meta_data"]["chat_id"] == "chat-9"
    assert notification.data["message"].startswith(f"[{_JOB}] ")


@pytest.mark.parametrize(
    ("job", "message"),
    [
        (_job(expires_at=datetime.now(UTC) - timedelta(minutes=1)), "end time"),
        (_job(max_fires=2, fire_count=2), "run 2 times"),
    ],
    ids=["expired", "max-fires"],
)
async def test_a_job_the_scheduler_pauses_by_itself_tells_the_user(bus: _RecordingBus, job: CronJob, message: str) -> None:
    stored = await _fire(job, _Runner())

    assert stored.status == JobStatus.PAUSED
    (notification,) = bus.notifications()
    assert notification.data["title"] == f"Scheduled task paused: {_JOB}"
    assert message in notification.data["message"]
    assert notification.data["meta_data"]["level"] == "warning"


async def test_a_one_shot_a_failure_pauses_tells_the_user_after_the_failed_run(bus: _RecordingBus) -> None:
    runner = _Runner()
    runner.result = JobResult(success=False, error="pump is dry")
    once = Schedule(kind=ScheduleKind.ONCE, run_at=datetime.now(UTC) + timedelta(hours=1))

    stored = await _fire(_job(schedule=once), runner)

    assert (stored.status, stored.paused_reason) == (JobStatus.PAUSED, PauseReason.RUN_FAILURES)
    failed, paused = (e.data for e in bus.notifications())
    assert failed["title"] == f"Scheduled task failed: {_JOB}"
    assert paused["title"] == f"Scheduled task paused: {_JOB}"
    assert "paused automatically" in paused["message"]
    assert paused["meta_data"]["level"] == "warning"


async def test_a_loop_guard_trip_is_told_by_the_pause_it_causes_alone(bus: _RecordingBus) -> None:
    runner = _Runner()
    runner.result = JobResult(success=False, error="RUNAWAY_CIRCUIT_BREAKER: pump repeated 5 times", circuit_broken=True)

    stored = await _fire(_job(), runner)

    assert (stored.status, stored.paused_reason) == (JobStatus.PAUSED, PauseReason.CIRCUIT_BREAK)
    (paused,) = (e.data for e in bus.notifications())
    assert paused["title"] == f"Scheduled task paused: {_JOB}"
    assert "paused automatically" in paused["message"]
    assert paused["meta_data"]["level"] == "warning"


async def test_a_run_a_crash_cut_short_tells_the_user_when_the_server_next_starts(bus: _RecordingBus) -> None:
    store = InMemoryCronStore()
    await store.save_job(_job())
    await store.mark_running("job-1")  # what a process that died under its run leaves behind
    scheduler = CronScheduler(store, {JobType.AGENT: _Runner()}, _Delivery(), config=CronConfig(), on_notice=publish_cron_notice)

    await scheduler.start()
    await scheduler.stop()

    (notification,) = bus.notifications()
    assert notification.data["title"] == f"Scheduled task interrupted: {_JOB}"
    assert notification.data["message"] == "The app stopped while it was running, so this run did not finish."
    assert notification.data["meta_data"]["level"] == "warning"
    assert notification.data["meta_data"]["chat_id"] == "chat-9"


async def test_a_crash_that_pauses_the_job_tells_the_user_after_the_interrupted_run(bus: _RecordingBus) -> None:
    store = InMemoryCronStore()
    await store.save_job(_job(consecutive_failures=2))
    await store.mark_running("job-1")
    scheduler = CronScheduler(store, {JobType.AGENT: _Runner()}, _Delivery(), config=CronConfig(), on_notice=publish_cron_notice)

    await scheduler.start()
    await scheduler.stop()

    stored = await store.get_job("job-1")
    assert stored is not None
    assert (stored.status, stored.paused_reason) == (JobStatus.PAUSED, PauseReason.RUN_FAILURES)
    interrupted, paused = (e.data for e in bus.notifications())
    assert interrupted["title"] == f"Scheduled task interrupted: {_JOB}"
    assert paused["title"] == f"Scheduled task paused: {_JOB}"
    assert paused["meta_data"]["level"] == "warning"


async def test_a_notice_raised_before_any_client_connects_is_waiting_for_the_first_one(monkeypatch: pytest.MonkeyPatch) -> None:
    """Recovery speaks while the server starts, before the web UI has opened its event stream."""
    real_bus = ServerEventBus()
    monkeypatch.setattr("app.core.cron.notifier.get_event_bus", lambda: real_bus)

    await publish_cron_notice(CronNotice(CronNoticeKind.RUN_INTERRUPTED, _JOB, chat_id="chat-1"))

    late_client = real_bus.subscribe()
    replayed = [late_client.get_nowait().event_type for _ in range(late_client.qsize())]
    assert replayed == [AppEventType.CRON_UPDATED, AppEventType.SYSTEM_NOTIFICATION]
