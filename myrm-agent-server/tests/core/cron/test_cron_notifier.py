"""``publish_cron_notice`` turns the cron engine's notices into the events the WebUI, voice and push channels read.

The engine states facts only; the notifier owns severity, wording and language. The last tests run the real
scheduler so a run outcome and an automatic pause both reach the event bus.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from myrm_agent_harness.toolkits.cron import CronConfig, CronNotice, CronNoticeKind, CronScheduler
from myrm_agent_harness.toolkits.cron.stores import InMemoryCronStore
from myrm_agent_harness.toolkits.cron.types import (
    CronJob,
    JobResult,
    JobStatus,
    JobType,
    Schedule,
    ScheduleKind,
)

from app.core.cron.notifier import publish_cron_notice
from app.services.event.app_event_bus import AppEvent, AppEventType

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
            CronNotice(CronNoticeKind.RUN_SUCCEEDED, _JOB, f"[{_JOB}] all watered", "chat-1"),
            "success",
            "voice_background_task_done",
            f"Reminder: {_JOB}",
            f"[{_JOB}] all watered",
        ),
        (
            CronNotice(CronNoticeKind.RUN_FAILED, _JOB, f"[{_JOB}] pump is dry", "chat-1"),
            "error",
            "voice_background_task_done",
            f"Scheduled task failed: {_JOB}",
            f"[{_JOB}] pump is dry",
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
    ],
    ids=["succeeded", "failed", "expired", "max-fires"],
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
    ("locale", "title", "pause_title", "max_fires_message"),
    [
        ("en", f"Reminder: {_JOB}", f"Scheduled task paused: {_JOB}", "It has run 3 times"),
        ("zh-CN", f"提醒：{_JOB}", f"定时任务已暂停：{_JOB}", "已执行 3 次"),
        ("zh-TW", f"提醒：{_JOB}", f"定時任務已暫停：{_JOB}", "已執行 3 次"),
        ("ja", f"リマインダー：{_JOB}", f"スケジュールタスクを一時停止しました：{_JOB}", "上限の 3 回"),
    ],
)
async def test_titles_and_messages_speak_the_users_language(
    bus: _RecordingBus,
    monkeypatch: pytest.MonkeyPatch,
    locale: str,
    title: str,
    pause_title: str,
    max_fires_message: str,
) -> None:
    _speak(monkeypatch, locale)

    await publish_cron_notice(CronNotice(CronNoticeKind.RUN_SUCCEEDED, _JOB, "x"))
    await publish_cron_notice(CronNotice(CronNoticeKind.JOB_MAX_FIRES_REACHED, _JOB, max_fires=3))

    run, pause = (e.data for e in bus.notifications())
    assert run["title"] == title
    assert pause["title"] == pause_title
    assert max_fires_message in pause["message"]


class _Delivery:
    async def deliver(self, job: CronJob, result: JobResult) -> None:
        return None


class _Runner:
    def __init__(self) -> None:
        self.result = JobResult(success=True, output="all watered")

    async def run(self, job: CronJob, *, context: str = "") -> JobResult:
        return self.result


async def _fire(job: CronJob, runner: _Runner) -> CronJob:
    """What the timer does for a due job, with the scheduler wired exactly as production wires it."""
    store = InMemoryCronStore()
    scheduler = CronScheduler(store, {JobType.AGENT: runner}, _Delivery(), config=CronConfig(), on_notice=publish_cron_notice)
    await store.save_job(job)
    await store.claim_due([job.id])
    snapshot = await store.get_job(job.id)
    assert snapshot is not None
    await scheduler._execute_and_persist(snapshot)
    stored = await store.get_job(job.id)
    assert stored is not None
    return stored


def _job(**overrides: object) -> CronJob:
    fields: dict[str, object] = {
        "id": "job-1",
        "user_id": "default",
        "name": _JOB,
        "job_type": JobType.AGENT,
        "schedule": Schedule(kind=ScheduleKind.INTERVAL, interval_ms=3_600_000, stagger_ms=0),
        "prompt": "prompt",
        "chat_id": "chat-9",
    }
    fields.update(overrides)
    return CronJob(**fields)


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
    ("overrides", "message"),
    [
        ({"expires_at": datetime.now(UTC) - timedelta(minutes=1)}, "end time"),
        ({"max_fires": 2, "fire_count": 2}, "run 2 times"),
    ],
    ids=["expired", "max-fires"],
)
async def test_a_job_the_scheduler_pauses_by_itself_tells_the_user(
    bus: _RecordingBus, overrides: dict[str, object], message: str
) -> None:
    stored = await _fire(_job(**overrides), _Runner())

    assert stored.status == JobStatus.PAUSED
    (notification,) = bus.notifications()
    assert notification.data["title"] == f"Scheduled task paused: {_JOB}"
    assert message in notification.data["message"]
    assert notification.data["meta_data"]["level"] == "warning"
