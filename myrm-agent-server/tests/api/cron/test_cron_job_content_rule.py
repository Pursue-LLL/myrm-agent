"""The cron REST API enforces one required-content rule on create and on update.

[INPUT] CronJobCreate/CronJobUpdate payloads, a real CronManager over an in-memory store.
[OUTPUT] Verified a script-only router job is created, and an edit that would leave a job with nothing to run is
refused with 400 and leaves the stored job untouched.
[POS] tests/api/cron/test_cron_job_content_rule.py
"""

from __future__ import annotations

from collections.abc import Generator
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from myrm_agent_harness.toolkits.cron import CronConfig, CronManager, CronScheduler
from myrm_agent_harness.toolkits.cron.stores import InMemoryCronStore

from app.api.cron.routes import helpers, jobs_router

_SCRIPT = "echo '{\"ok\": true}'"
_SCHEDULE = {"kind": "interval", "interval_ms": 3_600_000}


class _NoDelivery:
    async def deliver(self, job: object, result: object) -> None:
        pass


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    store = InMemoryCronStore()
    scheduler = CronScheduler(store=store, runners={}, delivery=_NoDelivery(), config=CronConfig())
    manager = CronManager(store, scheduler, shell_enabled=True)
    app = FastAPI()
    app.include_router(jobs_router, prefix="/cron")
    with patch.object(helpers, "_get_manager", return_value=manager):
        yield TestClient(app)


def _create(client: TestClient, **fields: object) -> dict[str, object]:
    response = client.post("/cron", json={"name": "job", "schedule": _SCHEDULE, **fields})
    assert response.status_code == 201, response.text
    body: dict[str, object] = response.json()
    return body


def test_script_mode_payload_creates_a_router_job_without_a_prompt(client: TestClient) -> None:
    created = _create(client, job_type="router", pre_condition_script=_SCRIPT)

    assert created["job_type"] == "router"
    assert created["prompt"] is None
    assert created["pre_condition_script"] == _SCRIPT


def test_router_job_with_neither_prompt_nor_script_is_refused(client: TestClient) -> None:
    response = client.post("/cron", json={"name": "job", "job_type": "router", "schedule": _SCHEDULE})

    assert response.status_code == 400
    assert "prompt" in response.json()["detail"]


def test_agent_prompt_cannot_be_emptied_by_an_edit(client: TestClient) -> None:
    job_id = _create(client, job_type="agent", prompt="sync the notes")["id"]

    response = client.patch(f"/cron/{job_id}", json={"prompt": ""})

    assert response.status_code == 400
    assert client.get(f"/cron/{job_id}").json()["prompt"] == "sync the notes"


def test_script_job_cannot_clear_its_script_when_it_has_no_prompt(client: TestClient) -> None:
    job_id = _create(client, job_type="router", pre_condition_script=_SCRIPT)["id"]

    response = client.patch(f"/cron/{job_id}", json={"pre_condition_script": None})

    assert response.status_code == 400
    assert client.get(f"/cron/{job_id}").json()["pre_condition_script"] == _SCRIPT


def test_script_job_may_drop_the_prompt_it_does_not_use(client: TestClient) -> None:
    job_id = _create(client, job_type="router", prompt="relay", pre_condition_script=_SCRIPT)["id"]

    response = client.patch(f"/cron/{job_id}", json={"prompt": ""})

    assert response.status_code == 200
    assert response.json()["pre_condition_script"] == _SCRIPT


def test_edit_that_does_not_touch_content_is_accepted(client: TestClient) -> None:
    job_id = _create(client, job_type="agent", prompt="sync the notes")["id"]

    response = client.patch(f"/cron/{job_id}", json={"name": "renamed"})

    assert response.status_code == 200
    assert response.json()["name"] == "renamed"
