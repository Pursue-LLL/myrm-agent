"""Unit tests for Multi-Surface Run State Projection API endpoints.

[INPUT]
- fastapi.FastAPI, starlette.testclient.TestClient
- app.api.runs.projection_router

[OUTPUT]
- Pytest test cases validating immutable run projections, attempt watermarks, and surface switching

[POS]
tests/api/runs/test_run_projection_api.py: Comprehensive test suite for MateClaw run projections.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api.runs.projection_router import projection_router


@pytest.fixture
def projection_client() -> TestClient:
    """Provide isolated TestClient mounting projection_router."""
    app = FastAPI()
    app.include_router(projection_router, prefix="/api/v1")
    return TestClient(app)


def test_get_run_projection_snapshot(projection_client: TestClient) -> None:
    """Verify GET /api/v1/runs/{run_id}/projection returns immutable full snapshot."""
    run_id = "run_mateclaw_demo_001"
    res = projection_client.get(f"/api/v1/runs/{run_id}/projection")
    assert res.status_code == 200
    data = res.json()

    assert data["run_id"] == run_id
    assert data["title"] == "Enterprise Microservice State Projection Refactor"
    assert data["status"] == "completed"
    assert data["active_surface"] == "runtime_console"
    assert data["current_attempt"] == 2
    assert len(data["attempts"]) == 2
    assert len(data["deliverables"]) >= 1
    assert len(data["audit_entries"]) >= 1
    assert len(data["events"]) >= 4

    # Verify attempt fault and retry watermarks
    attempt_1 = data["attempts"][0]
    assert attempt_1["status"] == "failed"
    assert "429 Too Many Requests" in attempt_1["error_reason"]

    attempt_2 = data["attempts"][1]
    assert attempt_2["status"] == "completed"
    assert attempt_2["tokens_per_sec"] > 200.0

    # 404 for unknown run
    not_found_res = projection_client.get("/api/v1/runs/unknown_run_9999/projection")
    assert not_found_res.status_code == 404


def test_get_run_events_stream(projection_client: TestClient) -> None:
    """Verify GET /api/v1/runs/{run_id}/events retrieves monotonic events."""
    run_id = "run_mateclaw_demo_001"
    res = projection_client.get(f"/api/v1/runs/{run_id}/events")
    assert res.status_code == 200
    events = res.json()
    assert isinstance(events, list)
    assert len(events) >= 4

    # Verify with since_ms filtering
    first_evt_ts = events[0]["timestamp_ms"]
    filtered_res = projection_client.get(f"/api/v1/runs/{run_id}/events?since_ms={first_evt_ts + 1}")
    assert filtered_res.status_code == 200
    filtered_events = filtered_res.json()
    assert len(filtered_events) <= len(events)


def test_switch_surface_viewport(projection_client: TestClient) -> None:
    """Verify POST /api/v1/runs/{run_id}/switch-surface updates focused projection surface."""
    run_id = "run_mateclaw_demo_001"
    res = projection_client.post(
        f"/api/v1/runs/{run_id}/switch-surface",
        json={"surface": "deliverables"},
    )
    assert res.status_code == 200
    assert res.json()["status"] == "ok"
    assert res.json()["active_surface"] == "deliverables"

    # Verify reflected in snapshot
    snap_res = projection_client.get(f"/api/v1/runs/{run_id}/projection")
    assert snap_res.json()["active_surface"] == "deliverables"


def test_record_new_attempt_telemetry(projection_client: TestClient) -> None:
    """Verify POST /api/v1/runs/{run_id}/attempts logs new attempt and updates totals."""
    run_id = "run_mateclaw_demo_001"
    payload = {
        "attempt_number": 3,
        "status": "completed",
        "tokens_in": 1200,
        "tokens_out": 800,
        "tokens_per_sec": 185.5,
        "duration_ms": 4200,
        "diff_summary": "1 file modified (+24 lines)",
    }
    res = projection_client.post(f"/api/v1/runs/{run_id}/attempts", json=payload)
    assert res.status_code == 201
    attempt = res.json()
    assert attempt["attempt_id"].startswith("att_")
    assert attempt["attempt_number"] == 3
    assert attempt["status"] == "completed"

    # Verify projection reflects updated current_attempt
    snap_res = projection_client.get(f"/api/v1/runs/{run_id}/projection")
    snap_data = snap_res.json()
    assert snap_data["current_attempt"] == 3
    assert len(snap_data["attempts"]) >= 3
