"""The cron REST API rejects an unrunnable schedule or resume with the manager's reason, and an activation books a slot.

[INPUT] The jobs and actions routers over a real CronManager and an in-memory store (the scheduler is never started).
[OUTPUT] Create and update answer 400 for a one-shot whose time has passed; resume answers 409 for a job that cannot
run and leaves an enabled job as it is; a PATCH that sets ``status`` to ``active`` is a resume (400 where it cannot
run): both book the next slot and clear the failure count. A manual run answers 202 once started, 409 while the job is
already running and 404 for a job that is missing or not active, and the refusals leave the job as it is.
[POS] tests/api/cron/test_cron_api_run_and_resume.py
"""

from __future__ import annotations

import asyncio
from collections.abc import Generator
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from myrm_agent_harness.toolkits.cron import CronConfig, CronManager, CronScheduler
from myrm_agent_harness.toolkits.cron.stores import InMemoryCronStore
from myrm_agent_harness.toolkits.cron.types import JobStatus, RunNowOutcome, Schedule, ScheduleKind

from app.api.cron.routes import actions_router, helpers, jobs_router

_HOUR = timedelta(hours=1)
_PASSED_ON_CREATE = "its scheduled time has passed; choose a future time"
_PASSED_ON_RESUME = "its scheduled time has passed; set a new time before resuming"
_EVERY_HOUR = {"kind": "interval", "interval_ms": 3_600_000, "stagger_ms": 0}


class _NoDelivery:
    async def deliver(self, job: object, result: object) -> None:
        pass


@dataclass
class Api:
    client: TestClient
    store: InMemoryCronStore
    manager: CronManager
    scheduler: CronScheduler

    def create(self, schedule: dict[str, object]) -> str:
        response = self.client.post(
            "/cron", json={"name": "reminder", "job_type": "agent", "schedule": schedule, "prompt": "remind me"}
        )
        assert response.status_code == 201, response.text
        return str(response.json()["id"])

    def rewrite(self, job_id: str, **changes: object) -> None:
        """Put the stored job into a state the API does not produce by itself (an auto-pause, a passed time)."""

        async def apply() -> None:
            job = await self.store.get_job(job_id)
            assert job is not None
            await self.store.save_job(replace(job, **changes))  # type: ignore[arg-type]

        asyncio.run(apply())

    def pause(self, job_id: str) -> None:
        assert self.client.post(f"/cron/{job_id}/pause").status_code == 200


@pytest.fixture
def api() -> Generator[Api, None, None]:
    store = InMemoryCronStore()
    scheduler = CronScheduler(store=store, runners={}, delivery=_NoDelivery(), config=CronConfig())
    manager = CronManager(store, scheduler, shell_enabled=True)
    app = FastAPI()
    app.include_router(actions_router, prefix="/cron")
    app.include_router(jobs_router, prefix="/cron")
    with patch.object(helpers, "_get_manager", return_value=manager):
        yield Api(TestClient(app), store, manager, scheduler)


def _once(offset: timedelta) -> dict[str, object]:
    return {"kind": "once", "run_at": (datetime.now(UTC) + offset).isoformat()}


def _passed_once() -> Schedule:
    return Schedule(kind=ScheduleKind.ONCE, run_at=datetime.now(UTC) - _HOUR)


def _instant(value: object) -> datetime:
    moment = datetime.fromisoformat(str(value))
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


class TestSchedulesThatCannotRun:
    def test_create_with_a_time_that_has_passed_is_a_400_and_stores_nothing(self, api: Api) -> None:
        response = api.client.post(
            "/cron", json={"name": "late", "job_type": "agent", "schedule": _once(-_HOUR), "prompt": "remind me"}
        )

        assert response.status_code == 400
        assert response.json()["detail"] == _PASSED_ON_CREATE
        assert api.client.get("/cron").json()["items"] == []

    def test_update_to_a_time_that_has_passed_is_a_400_and_keeps_the_job(self, api: Api) -> None:
        job_id = api.create(_once(_HOUR * 24))
        before = api.client.get(f"/cron/{job_id}").json()

        response = api.client.patch(f"/cron/{job_id}", json={"schedule": _once(-_HOUR)})

        assert response.status_code == 400
        assert response.json()["detail"] == _PASSED_ON_CREATE
        assert api.client.get(f"/cron/{job_id}").json() == before


class TestResume:
    def test_a_one_shot_whose_time_has_passed_is_a_409_and_stays_paused(self, api: Api) -> None:
        job_id = api.create(_once(_HOUR))
        api.pause(job_id)
        api.rewrite(job_id, schedule=_passed_once())

        response = api.client.post(f"/cron/{job_id}/resume")

        assert response.status_code == 409
        assert response.json()["detail"] == _PASSED_ON_RESUME
        assert api.client.get(f"/cron/{job_id}").json()["status"] == "paused"

    def test_a_completed_job_is_a_409(self, api: Api) -> None:
        job_id = api.create(_EVERY_HOUR)
        api.rewrite(job_id, status=JobStatus.COMPLETED)

        response = api.client.post(f"/cron/{job_id}/resume")

        assert response.status_code == 409
        assert response.json()["detail"] == "completed jobs cannot be resumed"

    def test_an_expired_job_is_a_409(self, api: Api) -> None:
        job_id = api.create(_EVERY_HOUR)
        api.pause(job_id)
        api.rewrite(job_id, expires_at=datetime.now(UTC) - _HOUR)

        response = api.client.post(f"/cron/{job_id}/resume")

        assert response.status_code == 409
        assert response.json()["detail"] == "job has expired; extend expires_at before resuming"

    def test_an_unknown_job_is_a_404(self, api: Api) -> None:
        assert api.client.post("/cron/nope/resume").status_code == 404

    def test_an_enabled_job_comes_back_unchanged(self, api: Api) -> None:
        job_id = api.create(_EVERY_HOUR)
        api.rewrite(job_id, consecutive_failures=2)
        before = api.client.get(f"/cron/{job_id}").json()

        response = api.client.post(f"/cron/{job_id}/resume")

        assert response.status_code == 200
        assert response.json() == before
        assert before["consecutive_failures"] == 2

    def test_books_the_next_slot_and_clears_the_failure_count(self, api: Api) -> None:
        job_id = api.create(_EVERY_HOUR)
        api.rewrite(job_id, status=JobStatus.PAUSED, next_run_at=None, consecutive_failures=3)

        started = datetime.now(UTC)
        response = api.client.post(f"/cron/{job_id}/resume")
        finished = datetime.now(UTC)

        assert response.status_code == 200
        body = response.json()
        assert (body["status"], body["consecutive_failures"]) == ("active", 0)
        assert started + _HOUR <= _instant(body["next_run_at"]) <= finished + _HOUR


class TestStatusPatch:
    def test_setting_active_is_a_resume_that_books_a_slot_and_clears_the_failures(self, api: Api) -> None:
        job_id = api.create(_EVERY_HOUR)
        api.rewrite(job_id, status=JobStatus.PAUSED, next_run_at=None, consecutive_failures=3)

        started = datetime.now(UTC)
        response = api.client.patch(f"/cron/{job_id}", json={"status": "active"})
        finished = datetime.now(UTC)

        assert response.status_code == 200
        body = response.json()
        assert (body["status"], body["consecutive_failures"]) == ("active", 0)
        assert started + _HOUR <= _instant(body["next_run_at"]) <= finished + _HOUR

    def test_setting_active_on_a_job_that_cannot_run_is_a_400_and_stays_paused(self, api: Api) -> None:
        job_id = api.create(_EVERY_HOUR)
        api.pause(job_id)
        api.rewrite(job_id, expires_at=datetime.now(UTC) - _HOUR)

        response = api.client.patch(f"/cron/{job_id}", json={"status": "active"})

        assert response.status_code == 400
        assert response.json()["detail"] == "job has expired; extend expires_at before resuming"
        assert api.client.get(f"/cron/{job_id}").json()["status"] == "paused"

    def test_an_edit_that_removes_the_obstacle_activates_in_the_same_call(self, api: Api) -> None:
        job_id = api.create(_EVERY_HOUR)
        api.pause(job_id)
        api.rewrite(job_id, expires_at=datetime.now(UTC) - _HOUR)

        response = api.client.patch(
            f"/cron/{job_id}", json={"status": "active", "expires_at": (datetime.now(UTC) + _HOUR * 24).isoformat()}
        )

        assert response.status_code == 200
        assert response.json()["status"] == "active"


class TestTrigger:
    def test_a_started_run_is_a_202(self, api: Api) -> None:
        job_id = api.create(_EVERY_HOUR)

        with patch.object(api.manager, "run_now", AsyncMock(return_value=RunNowOutcome.STARTED)) as run_now:
            response = api.client.post(f"/cron/{job_id}/trigger")

        assert (response.status_code, response.json()) == (202, {"triggered": True})
        run_now.assert_awaited_once_with(job_id)

    def test_a_job_that_is_already_running_is_a_409_and_is_left_alone(self, api: Api) -> None:
        job_id = api.create(_EVERY_HOUR)
        before = api.client.get(f"/cron/{job_id}").json()
        api.scheduler._in_flight[job_id] += 1  # a run that has started and not yet ended

        response = api.client.post(f"/cron/{job_id}/trigger")

        assert (response.status_code, response.json()["detail"]) == (409, "Job is already running")
        assert api.client.get(f"/cron/{job_id}").json() == before

    def test_a_job_that_is_missing_or_not_active_is_a_404(self, api: Api) -> None:
        paused_id = api.create(_EVERY_HOUR)
        api.pause(paused_id)

        for job_id in ("nope", paused_id):
            response = api.client.post(f"/cron/{job_id}/trigger")

            assert (response.status_code, response.json()["detail"]) == (404, "Job not found or not active")
        assert api.scheduler._in_flight == {}
