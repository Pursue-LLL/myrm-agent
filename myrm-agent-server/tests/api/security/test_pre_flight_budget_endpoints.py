"""API endpoint tests for Live Pre-Flight Budget Chokepoint Suite in myrm-agent-server."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.security.pre_flight_budget_router import (
    router as pre_flight_budget_router,
)
from app.services.security.pre_flight_budget_service import PreFlightBudgetService


@pytest.fixture
def client() -> TestClient:
    PreFlightBudgetService.reset_instance()
    app = FastAPI()
    app.include_router(pre_flight_budget_router, prefix="/api/v1/security")
    return TestClient(app)


def test_budget_config_endpoints(client: TestClient) -> None:
    # 1. Config not found initially
    resp_get_missing = client.get("/api/v1/security/pre-flight-budget/config/proj_test_1")
    assert resp_get_missing.status_code == 404

    # 2. Create config
    resp_create = client.post(
        "/api/v1/security/pre-flight-budget/config",
        json={
            "project_id": "proj_test_1",
            "limit_amount": 15.0,
            "currency": "USD",
            "period": "daily",
            "action": "pause",
        },
    )
    assert resp_create.status_code == 201
    data_create = resp_create.json()
    assert data_create["project_id"] == "proj_test_1"
    assert data_create["limit_amount"] == 15.0

    # 3. Retrieve config
    resp_get = client.get("/api/v1/security/pre-flight-budget/config/proj_test_1")
    assert resp_get.status_code == 200
    assert resp_get.json()["limit_amount"] == 15.0


def test_spend_evaluate_and_enforce_endpoints(client: TestClient) -> None:
    # Create config with limit 10.0
    client.post(
        "/api/v1/security/pre-flight-budget/config",
        json={
            "project_id": "proj_test_2",
            "limit_amount": 10.0,
            "currency": "USD",
            "period": "daily",
            "action": "stop",
        },
    )

    # 1. Record spend under limit
    resp_spend = client.post(
        "/api/v1/security/pre-flight-budget/spend",
        json={
            "project_id": "proj_test_2",
            "amount": 4.0,
            "currency": "USD",
            "model_name": "gpt-4o",
        },
    )
    assert resp_spend.status_code == 201
    assert resp_spend.json()["amount"] == 4.0

    # 2. Evaluate under limit
    resp_eval = client.post(
        "/api/v1/security/pre-flight-budget/evaluate",
        json={"project_id": "proj_test_2"},
    )
    assert resp_eval.status_code == 200
    assert not resp_eval.json()["tripped"]
    assert resp_eval.json()["current_spend"] == 4.0

    # 3. Enforce under limit -> passes
    resp_enforce = client.post(
        "/api/v1/security/pre-flight-budget/enforce",
        json={"project_id": "proj_test_2"},
    )
    assert resp_enforce.status_code == 200
    assert not resp_enforce.json()["tripped"]

    # 4. Check queue allowed
    resp_queue = client.get("/api/v1/security/pre-flight-budget/queue-allowed/proj_test_2")
    assert resp_queue.status_code == 200
    assert resp_queue.json()["queue_dispatch_allowed"]

    # 5. Record spend to exceed limit (4.0 + 7.0 = 11.0 >= 10.0)
    client.post(
        "/api/v1/security/pre-flight-budget/spend",
        json={
            "project_id": "proj_test_2",
            "amount": 7.0,
            "currency": "USD",
        },
    )

    # 6. Evaluate over limit -> tripped=True
    resp_eval_over = client.post(
        "/api/v1/security/pre-flight-budget/evaluate",
        json={"project_id": "proj_test_2"},
    )
    assert resp_eval_over.status_code == 200
    assert resp_eval_over.json()["tripped"]

    # 7. Enforce over limit -> HTTP 429 Hard Gate Tripped
    resp_enforce_over = client.post(
        "/api/v1/security/pre-flight-budget/enforce",
        json={"project_id": "proj_test_2"},
    )
    assert resp_enforce_over.status_code == 429
    assert resp_enforce_over.json()["detail"]["decision"]["tripped"]

    # 8. Queue locked
    resp_queue_over = client.get(
        "/api/v1/security/pre-flight-budget/queue-allowed/proj_test_2"
    )
    assert resp_queue_over.status_code == 200
    assert not resp_queue_over.json()["queue_dispatch_allowed"]


def test_broadcast_events_endpoint(client: TestClient) -> None:
    client.post(
        "/api/v1/security/pre-flight-budget/config",
        json={
            "project_id": "proj_events_api",
            "limit_amount": 5.0,
        },
    )
    client.post(
        "/api/v1/security/pre-flight-budget/spend",
        json={
            "project_id": "proj_events_api",
            "amount": 2.0,
        },
    )

    resp_events = client.get(
        "/api/v1/security/pre-flight-budget/events?project_id=proj_events_api"
    )
    assert resp_events.status_code == 200
    events = resp_events.json()
    assert len(events) >= 1
    assert events[0]["project_id"] == "proj_events_api"
