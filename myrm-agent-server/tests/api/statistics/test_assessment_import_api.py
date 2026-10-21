from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.support.minimal_app import build_minimal_app

app = build_minimal_app("notifications", preset="statistics")


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _get_summary(client: TestClient) -> dict[str, object]:
    response = client.get(
        "/api/v1/statistics/assessment-import/summary?days=365",
        headers={"Authorization": "Bearer local"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    return payload["data"]


def test_assessment_import_summary_accumulates_metrics(client: TestClient) -> None:
    before = _get_summary(client)

    events = [
        {
            "event_type": "import_attempted",
            "surface": "project_milestone_panel",
            "trigger": "manual_input",
            "context_key": "project:alpha",
        },
        {
            "event_type": "import_attempted",
            "surface": "project_milestone_panel",
            "trigger": "recent_candidate",
            "context_key": "project:alpha",
        },
        {
            "event_type": "import_succeeded",
            "surface": "project_milestone_panel",
            "trigger": "recent_candidate",
            "context_key": "project:alpha",
        },
        {
            "event_type": "import_failed",
            "surface": "project_milestone_panel",
            "trigger": "manual_input",
            "context_key": "project:alpha",
            "failure_reason": "artifact_not_found",
        },
        {
            "event_type": "dropped_report",
            "surface": "project_milestone_panel",
            "trigger": "manual_input",
            "context_key": "project:alpha",
            "count": 2,
        },
    ]
    for event in events:
        response = client.post(
            "/api/v1/statistics/assessment-import/events",
            json=event,
            headers={"Authorization": "Bearer local"},
        )
        assert response.status_code == 200
        assert response.json()["success"] is True

    after = _get_summary(client)

    assert int(after["import_attempted_count"]) >= int(before["import_attempted_count"]) + 2
    assert int(after["import_succeeded_count"]) >= int(before["import_succeeded_count"]) + 1
    assert int(after["import_failed_count"]) >= int(before["import_failed_count"]) + 1
    assert int(after["dropped_event_count"]) >= int(before["dropped_event_count"]) + 2

    attempts_by_trigger = after["attempts_by_trigger"]
    assert isinstance(attempts_by_trigger, dict)
    assert "manual_input" in attempts_by_trigger
    assert "recent_candidate" in attempts_by_trigger

    failure_reason_breakdown = after["failure_reason_breakdown"]
    assert isinstance(failure_reason_breakdown, dict)
    assert int(failure_reason_breakdown.get("artifact_not_found", 0)) >= 1


def test_assessment_import_rejects_failure_reason_for_non_failed_event(client: TestClient) -> None:
    response = client.post(
        "/api/v1/statistics/assessment-import/events",
        json={
            "event_type": "import_attempted",
            "surface": "project_milestone_panel",
            "trigger": "manual_input",
            "failure_reason": "artifact_not_found",
        },
        headers={"Authorization": "Bearer local"},
    )
    assert response.status_code == 400


def test_assessment_import_defaults_failure_reason_for_failed_event(client: TestClient) -> None:
    response = client.post(
        "/api/v1/statistics/assessment-import/events",
        json={
            "event_type": "import_failed",
            "surface": "project_milestone_panel",
            "trigger": "recent_candidate",
            "context_key": "project:beta",
        },
        headers={"Authorization": "Bearer local"},
    )
    assert response.status_code == 200
    assert response.json()["success"] is True

    summary = _get_summary(client)
    breakdown = summary["failure_reason_breakdown"]
    assert isinstance(breakdown, dict)
    assert int(breakdown.get("unknown_error", 0)) >= 1


def test_assessment_import_rejects_non_dropped_count(client: TestClient) -> None:
    response = client.post(
        "/api/v1/statistics/assessment-import/events",
        json={
            "event_type": "import_succeeded",
            "surface": "project_milestone_panel",
            "trigger": "recent_candidate",
            "count": 3,
        },
        headers={"Authorization": "Bearer local"},
    )
    assert response.status_code == 400
