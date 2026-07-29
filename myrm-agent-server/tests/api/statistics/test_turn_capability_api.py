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
        "/api/v1/statistics/turn-capability/summary?days=365",
        headers={"Authorization": "Bearer local"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    return payload["data"]


def test_turn_capability_summary_accumulates_metrics(client: TestClient) -> None:
    before = _get_summary(client)

    events = [
        {
            "event_type": "selection_submitted",
            "source": "direct",
            "context_key": "chat:test",
            "selected_skill_count": 2,
            "selected_mcp_count": 1,
        },
        {
            "event_type": "override_applied",
            "source": "direct",
            "context_key": "chat:test",
            "selected_skill_count": 2,
            "selected_mcp_count": 1,
            "effective_skill_count": 2,
            "effective_mcp_count": 1,
        },
        {
            "event_type": "queue_enqueued",
            "source": "busy_requeue",
            "context_key": "chat:test",
            "selected_skill_count": 2,
            "selected_mcp_count": 1,
        },
        {
            "event_type": "busy_requeued",
            "source": "busy_requeue",
            "context_key": "chat:test",
        },
        {
            "event_type": "send_completed",
            "source": "queue_drain",
            "context_key": "chat:test",
            "effective_skill_count": 2,
            "effective_mcp_count": 1,
        },
        {
            "event_type": "send_failed",
            "source": "direct",
            "context_key": "chat:test",
            "failure_reason": "network_error",
        },
        {
            "event_type": "override_noop",
            "source": "direct",
            "context_key": "chat:test",
            "selected_skill_count": 1,
        },
        {
            "event_type": "dropped_report",
            "source": "queue_submit",
            "context_key": "chat:test",
            "count": 3,
        },
    ]
    for event in events:
        response = client.post(
            "/api/v1/statistics/turn-capability/events",
            json=event,
            headers={"Authorization": "Bearer local"},
        )
        assert response.status_code == 200
        assert response.json()["success"] is True

    after = _get_summary(client)

    assert int(after["selection_submitted_count"]) >= int(before["selection_submitted_count"]) + 1
    assert int(after["override_applied_count"]) >= int(before["override_applied_count"]) + 1
    assert int(after["override_noop_count"]) >= int(before["override_noop_count"]) + 1
    assert int(after["queue_enqueued_count"]) >= int(before["queue_enqueued_count"]) + 1
    assert int(after["send_completed_count"]) >= int(before["send_completed_count"]) + 1
    assert int(after["send_failed_count"]) >= int(before["send_failed_count"]) + 1
    assert int(after["busy_requeued_count"]) >= int(before["busy_requeued_count"]) + 1
    assert int(after["dropped_event_count"]) >= int(before["dropped_event_count"]) + 3

    assert float(after["apply_rate"]) >= 0
    assert float(after["completion_rate"]) >= 0
    assert float(after["failure_rate"]) >= 0
    assert float(after["avg_selected_skill_count"]) >= 0
    assert float(after["avg_effective_skill_count"]) >= 0

    submitted_by_source = after["submitted_by_source"]
    assert isinstance(submitted_by_source, dict)
    assert "direct" in submitted_by_source
    assert "queue_submit" in submitted_by_source
    assert "queue_drain" in submitted_by_source
    assert "busy_requeue" in submitted_by_source

    failure_reason_breakdown = after["failure_reason_breakdown"]
    assert isinstance(failure_reason_breakdown, dict)
    assert int(failure_reason_breakdown.get("network_error", 0)) >= 1


def test_turn_capability_rejects_failure_reason_for_non_failed_event(client: TestClient) -> None:
    response = client.post(
        "/api/v1/statistics/turn-capability/events",
        json={
            "event_type": "selection_submitted",
            "source": "direct",
            "failure_reason": "network_error",
        },
        headers={"Authorization": "Bearer local"},
    )
    assert response.status_code == 400


def test_turn_capability_rejects_invalid_failure_reason_enum(client: TestClient) -> None:
    response = client.post(
        "/api/v1/statistics/turn-capability/events",
        json={
            "event_type": "send_failed",
            "source": "direct",
            "failure_reason": "AgentBusyError",
        },
        headers={"Authorization": "Bearer local"},
    )
    assert response.status_code == 422


def test_turn_capability_defaults_failure_reason_for_send_failed(client: TestClient) -> None:
    response = client.post(
        "/api/v1/statistics/turn-capability/events",
        json={
            "event_type": "send_failed",
            "source": "direct",
            "context_key": "chat:reason-default",
        },
        headers={"Authorization": "Bearer local"},
    )
    assert response.status_code == 200
    assert response.json()["success"] is True

    summary = _get_summary(client)
    failure_reason_breakdown = summary["failure_reason_breakdown"]
    assert isinstance(failure_reason_breakdown, dict)
    assert int(failure_reason_breakdown.get("unknown_error", 0)) >= 1


def test_turn_capability_rejects_non_dropped_count(client: TestClient) -> None:
    response = client.post(
        "/api/v1/statistics/turn-capability/events",
        json={
            "event_type": "selection_submitted",
            "source": "direct",
            "count": 2,
        },
        headers={"Authorization": "Bearer local"},
    )
    assert response.status_code == 400


def test_turn_capability_requires_effective_counts_for_override_applied(client: TestClient) -> None:
    response = client.post(
        "/api/v1/statistics/turn-capability/events",
        json={
            "event_type": "override_applied",
            "source": "direct",
            "selected_skill_count": 2,
            "selected_mcp_count": 1,
        },
        headers={"Authorization": "Bearer local"},
    )
    assert response.status_code == 400
