"""GET /cron/{job_id}/delivery-health: how the route finds a job's destination and shapes the service's verdict.

[INPUT]
- app.api.cron.routes::delivery_health_router, router (POS: the route under test, and the whole cron router it must stay reachable in)
- app.api.cron.routes.helpers::_get_manager (POS: manager accessor, replaced here by a stand-in manager)
- app.services.cron.delivery_health_service::DeliveryHealth, DeliveryHealthService, DeliveryHealthStatus (POS: the judgment the route reads, replaced here by fixed verdicts)

[OUTPUT]
- The service is asked about the job's saved delivery (channel and address); an unknown job is a 404
- A verdict becomes exactly four fields, status and category as plain strings and the failure time as a UTC moment; no
  verdict is a 204 without a body, which the web client's request helper reads as "nothing" (a ``null`` body makes it throw)
- The route is mounted on the whole cron router, so it is served where the app mounts that router

[POS]
The judgment itself is covered over real rows in test_delivery_health_service.py; this covers only the route's own
lookup and mapping.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient
from myrm_agent_harness.api import ConnectorErrorCategory
from myrm_agent_harness.toolkits.cron import CronJob, DeliveryConfig, JobType, Schedule, ScheduleKind

from app.api.cron.routes import delivery_health_router, helpers
from app.api.cron.routes import router as cron_router
from app.services.cron.delivery_health_service import DeliveryHealth, DeliveryHealthService, DeliveryHealthStatus

_FAILED_AT = datetime(2026, 1, 1, 0, 5, tzinfo=UTC)
_ADDRESS = "https://api.example.com/webhook"
_JOB = CronJob(
    id="job-1",
    name="report",
    job_type=JobType.ROUTER,
    schedule=Schedule(kind=ScheduleKind.INTERVAL, interval_ms=3_600_000),
    command="__probe__",
    delivery=DeliveryConfig(channel="webhook", target=_ADDRESS),
)
_DEGRADED = DeliveryHealth(
    DeliveryHealthStatus.DEGRADED,
    failure_streak=2,
    last_error_category=ConnectorErrorCategory.HTTP_SERVER_ERROR,
    last_failed_at=_FAILED_AT,
)

ClientFor = Callable[[APIRouter, CronJob | None], TestClient]


@pytest.fixture
def client_for(monkeypatch: pytest.MonkeyPatch) -> ClientFor:
    """A client over ``router`` whose job store knows ``job`` (or nothing)."""

    def build(router: APIRouter, job: CronJob | None) -> TestClient:
        manager = MagicMock()
        manager.get_job = AsyncMock(return_value=job)
        monkeypatch.setattr(helpers, "_get_manager", lambda: manager)
        app = FastAPI()
        app.include_router(router, prefix="/cron")
        return TestClient(app)

    return build


def test_a_verdict_becomes_four_plain_fields(client_for: ClientFor) -> None:
    client = client_for(delivery_health_router, _JOB)

    with patch.object(DeliveryHealthService, "get_destination_health", new=AsyncMock(return_value=_DEGRADED)):
        response = client.get("/cron/job-1/delivery-health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "degraded",
        "failure_streak": 2,
        "last_error_category": "http_server_error",
        "last_failed_at": "2026-01-01T00:05:00Z",
    }


def test_a_destination_without_a_verdict_is_a_204_without_a_body(client_for: ClientFor) -> None:
    client = client_for(delivery_health_router, _JOB)

    with patch.object(DeliveryHealthService, "get_destination_health", new=AsyncMock(return_value=None)):
        response = client.get("/cron/job-1/delivery-health")

    assert response.status_code == 204
    assert response.content == b""


def test_the_service_is_asked_about_the_saved_delivery_of_the_job(client_for: ClientFor) -> None:
    client = client_for(delivery_health_router, _JOB)
    serving = AsyncMock(return_value=None)

    with patch.object(DeliveryHealthService, "get_destination_health", new=serving):
        client.get("/cron/job-1/delivery-health")

    serving.assert_awaited_once_with("webhook", _ADDRESS)


def test_an_unknown_job_is_a_404(client_for: ClientFor) -> None:
    client = client_for(delivery_health_router, None)
    serving = AsyncMock(return_value=None)

    with patch.object(DeliveryHealthService, "get_destination_health", new=serving):
        response = client.get("/cron/missing/delivery-health")

    assert response.status_code == 404
    serving.assert_not_awaited()


def test_the_route_is_reachable_through_the_whole_cron_router(client_for: ClientFor) -> None:
    client = client_for(cron_router, _JOB)

    with patch.object(DeliveryHealthService, "get_destination_health", new=AsyncMock(return_value=_DEGRADED)):
        response = client.get("/cron/job-1/delivery-health")

    assert response.status_code == 200
    assert response.json()["status"] == "degraded"
