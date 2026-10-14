"""GET /api/v1/health/resources only reports; it never repairs a resource."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from myrm_agent_harness.infra.health.health_checker import HealthCheckResult, HealthStatus


@pytest.fixture
def client() -> TestClient:
    from tests.support.minimal_app import build_minimal_app

    app: FastAPI = build_minimal_app(preset="health")
    return TestClient(app)


def _checks_result() -> tuple[bool, list[tuple[str, HealthCheckResult, None]]]:
    return False, [
        ("sqlite", HealthCheckResult(status=HealthStatus.UNHEALTHY, message="quick_check failed"), None),
        ("qdrant", HealthCheckResult(status=HealthStatus.HEALTHY, message="ok", details={"collections": 2}), None),
    ]


def test_resources_reports_each_checker(client: TestClient) -> None:
    runner = AsyncMock(return_value=_checks_result())
    with patch("app.core.infra.health.run_all_health_checks", runner):
        response = client.get("/api/v1/health/resources")

    assert response.status_code == 200
    body = response.json()
    assert body["all_healthy"] is False
    assert [(item["name"], item["status"]) for item in body["resources"]] == [
        ("sqlite", HealthStatus.UNHEALTHY.value),
        ("qdrant", HealthStatus.HEALTHY.value),
    ]
    assert body["resources"][1]["details"] == {"collections": 2}


def test_resources_never_triggers_recovery_even_when_the_caller_asks_for_it(client: TestClient) -> None:
    runner = AsyncMock(return_value=_checks_result())
    with patch("app.core.infra.health.run_all_health_checks", runner):
        response = client.get("/api/v1/health/resources", params={"auto_recover": "true", "force_recovery": "true"})

    assert response.status_code == 200
    runner.assert_awaited_once_with(auto_recover=False)
    assert "recovery" not in response.text


def test_resources_failure_is_a_generic_500(client: TestClient) -> None:
    runner = AsyncMock(side_effect=RuntimeError("secret path /Users/someone/db"))
    with patch("app.core.infra.health.run_all_health_checks", runner):
        response = client.get("/api/v1/health/resources")

    assert response.status_code == 500
    assert response.json()["detail"] == "Resource health check failed"
