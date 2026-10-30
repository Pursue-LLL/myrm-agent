"""The "skip if the previous run is still going" flag round-trips through the cron REST API.

[INPUT] CronJobCreate/CronJobUpdate payloads carrying skip_if_active, a real CronManager over an in-memory store.
[OUTPUT] Verified create stores the flag, update changes it only when sent, and responses report the stored value.
[POS] tests/api/cron/test_cron_skip_if_active.py
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


def _create(client: TestClient, **extra: object) -> dict[str, object]:
    response = client.post(
        "/cron",
        json={
            "name": "hourly-sync",
            "job_type": "agent",
            "schedule": {"kind": "interval", "interval_ms": 3_600_000},
            "prompt": "sync the notes",
            **extra,
        },
    )
    assert response.status_code == 201
    return response.json()


def test_create_stores_the_flag_and_the_response_reports_it(client: TestClient) -> None:
    created = _create(client, skip_if_active=True)

    assert created["skip_if_active"] is True
    assert client.get(f"/cron/{created['id']}").json()["skip_if_active"] is True


def test_the_flag_is_off_unless_the_request_sets_it(client: TestClient) -> None:
    assert _create(client)["skip_if_active"] is False


def test_update_changes_the_flag_only_when_the_request_sends_it(client: TestClient) -> None:
    job_id = _create(client)["id"]

    assert client.patch(f"/cron/{job_id}", json={"skip_if_active": True}).json()["skip_if_active"] is True
    assert client.patch(f"/cron/{job_id}", json={"name": "renamed"}).json()["skip_if_active"] is True
    assert client.patch(f"/cron/{job_id}", json={"skip_if_active": False}).json()["skip_if_active"] is False
