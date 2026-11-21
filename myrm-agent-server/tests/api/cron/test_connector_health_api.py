"""GET /cron/connectors/health: how the route shapes the service's summaries into its response.

[INPUT]
- app.api.cron.routes::connector_health_router (POS: the route under test)
- app.services.cron.connector_health_service::ConnectorHealthService, ConnectorHealthSummary (POS: the aggregation the route reads, replaced here by fixed summaries)

[OUTPUT]
- Each summary becomes one item whose status and error category are plain strings; the item holds nothing else than the
  summary produces
- The degraded and down counts tally the items by status
- ``window_hours`` reaches the service, defaults to a day and is bounded to a week

[POS]
The aggregation itself is covered over real rows in test_connector_health_service.py; this covers only the route's
own mapping and parameter handling.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from myrm_agent_harness.api import ConnectorErrorCategory, ConnectorHealthStatus

from app.api.cron.routes import connector_health_router
from app.services.cron.connector_health_service import ConnectorHealthService, ConnectorHealthSummary

_FAILED_AT = datetime(2026, 1, 1, 0, 5, tzinfo=UTC)


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(connector_health_router, prefix="/cron")
    return TestClient(app)


def _summary(
    status: ConnectorHealthStatus,
    *,
    streak: int = 0,
    category: ConnectorErrorCategory | None = None,
    message: str | None = None,
    failed_at: datetime | None = None,
) -> ConnectorHealthSummary:
    return ConnectorHealthSummary(
        target="https://api.example.com/webhook",
        channel="webhook",
        status=status,
        total_deliveries=10,
        failed_deliveries=streak,
        consecutive_failures=streak,
        last_error_category=category,
        last_error_message=message,
        last_failed_at=failed_at,
        bound_job_ids=("job-1",),
    )


def _serving(*summaries: ConnectorHealthSummary) -> AsyncMock:
    return AsyncMock(return_value=list(summaries))


def test_a_summary_becomes_one_item_with_plain_strings(client: TestClient) -> None:
    summary = _summary(
        ConnectorHealthStatus.DEGRADED,
        streak=2,
        category=ConnectorErrorCategory.HTTP_SERVER_ERROR,
        message="Webhook returned 502: Bad Gateway",
        failed_at=_FAILED_AT,
    )

    with patch.object(ConnectorHealthService, "get_all_connectors_health", new=_serving(summary)):
        response = client.get("/cron/connectors/health")

    assert response.status_code == 200
    [item] = response.json()["items"]
    assert set(item) == {
        "target",
        "channel",
        "status",
        "total_deliveries",
        "failed_deliveries",
        "consecutive_failures",
        "last_error_category",
        "last_error_message",
        "last_delivery_at",
        "last_failed_at",
        "bound_job_ids",
    }
    assert item["status"] == "degraded"
    assert item["last_error_category"] == "http_server_error"
    assert item["last_error_message"] == "Webhook returned 502: Bad Gateway"
    assert datetime.fromisoformat(item["last_failed_at"]) == _FAILED_AT
    assert item["last_delivery_at"] is None
    assert item["bound_job_ids"] == ["job-1"]


def test_the_counts_tally_the_items_by_status(client: TestClient) -> None:
    summaries = (
        _summary(ConnectorHealthStatus.HEALTHY),
        _summary(ConnectorHealthStatus.DEGRADED),
        _summary(ConnectorHealthStatus.DOWN),
        _summary(ConnectorHealthStatus.DOWN),
    )

    with patch.object(ConnectorHealthService, "get_all_connectors_health", new=_serving(*summaries)):
        data = client.get("/cron/connectors/health").json()

    assert (data["total"], data["degraded_count"], data["down_count"]) == (4, 1, 2)


@pytest.mark.parametrize(("query", "window_hours"), [("", 24), ("?window_hours=12", 12)])
def test_the_window_reaches_the_service(client: TestClient, query: str, window_hours: int) -> None:
    serving = _serving()

    with patch.object(ConnectorHealthService, "get_all_connectors_health", new=serving):
        response = client.get(f"/cron/connectors/health{query}")

    assert response.status_code == 200
    serving.assert_awaited_once_with(window_hours=window_hours)


@pytest.mark.parametrize("window_hours", [0, 169])
def test_a_window_outside_a_week_is_refused(client: TestClient, window_hours: int) -> None:
    serving = _serving()

    with patch.object(ConnectorHealthService, "get_all_connectors_health", new=serving):
        response = client.get(f"/cron/connectors/health?window_hours={window_hours}")

    assert response.status_code == 422
    serving.assert_not_awaited()
