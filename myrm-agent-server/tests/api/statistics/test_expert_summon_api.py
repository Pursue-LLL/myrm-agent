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
        "/api/v1/statistics/expert-summon/summary?days=365",
        headers={"Authorization": "Bearer local"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    return payload["data"]


def test_expert_summon_summary_accumulates_metrics(client: TestClient) -> None:
    before = _get_summary(client)

    events = [
        {"event_type": "surface_viewed", "surface": "template_market", "context_key": "template-market"},
        {
            "event_type": "search_used",
            "surface": "template_market",
            "context_key": "template-market",
            "query_length": 12,
        },
        {
            "event_type": "summon_attempted",
            "surface": "template_market",
            "context_key": "template-market",
            "trigger": "use_case_chip",
            "template_kind": "team",
            "from_search": True,
            "used_use_case": True,
        },
        {
            "event_type": "summon_succeeded",
            "surface": "template_market",
            "context_key": "template-market",
            "trigger": "use_case_chip",
            "template_kind": "team",
            "from_search": True,
            "used_use_case": True,
        },
        {
            "event_type": "summon_failed",
            "surface": "flow_pad_inline",
            "context_key": "flowpad:inline",
            "trigger": "template_card",
            "failure_reason": "network_error",
        },
        {
            "event_type": "route_applied",
            "surface": "flow_pad_inline",
            "context_key": "flowpad:inline",
            "trigger": "use_case_chip",
            "template_kind": "team",
            "from_search": True,
            "used_use_case": True,
        },
        {
            "event_type": "route_apply_failed",
            "surface": "flow_pad_inline",
            "context_key": "flowpad:inline",
            "trigger": "template_card",
            "failure_reason": "route_apply_failed",
        },
        {
            "event_type": "first_message_sent",
            "surface": "flow_pad_inline",
            "context_key": "flowpad:inline",
            "trigger": "use_case_chip",
            "template_kind": "team",
            "from_search": True,
            "used_use_case": True,
        },
        {
            "event_type": "dropped_report",
            "surface": "template_market",
            "context_key": "template-market",
            "count": 2,
        },
    ]
    for event in events:
        response = client.post(
            "/api/v1/statistics/expert-summon/events",
            json=event,
            headers={"Authorization": "Bearer local"},
        )
        assert response.status_code == 200
        assert response.json()["success"] is True

    after = _get_summary(client)

    assert int(after["surface_viewed_count"]) >= int(before["surface_viewed_count"]) + 1
    assert int(after["search_used_count"]) >= int(before["search_used_count"]) + 1
    assert int(after["summon_attempted_count"]) >= int(before["summon_attempted_count"]) + 1
    assert int(after["summon_succeeded_count"]) >= int(before["summon_succeeded_count"]) + 1
    assert int(after["summon_failed_count"]) >= int(before["summon_failed_count"]) + 1
    assert int(after["route_applied_count"]) >= int(before["route_applied_count"]) + 1
    assert int(after["route_apply_failed_count"]) >= int(before["route_apply_failed_count"]) + 1
    assert int(after["first_message_sent_count"]) >= int(before["first_message_sent_count"]) + 1
    assert int(after["dropped_event_count"]) >= int(before["dropped_event_count"]) + 2

    assert float(after["summon_success_rate"]) >= 0
    assert float(after["first_message_sent_rate"]) >= 0
    assert float(after["route_apply_rate"]) >= 0
    assert float(after["avg_search_query_length"]) >= 0
    assert float(after["use_case_trigger_rate"]) >= 0
    assert float(after["search_assisted_summon_rate"]) >= 0

    viewed_by_surface = after["viewed_by_surface"]
    assert isinstance(viewed_by_surface, dict)
    assert "template_market" in viewed_by_surface
    assert "flow_pad_inline" in viewed_by_surface

    attempted_by_trigger = after["attempted_by_trigger"]
    assert isinstance(attempted_by_trigger, dict)
    assert "template_card" in attempted_by_trigger
    assert "use_case_chip" in attempted_by_trigger
    assert "route_menu" in attempted_by_trigger

    failure_reason_breakdown = after["failure_reason_breakdown"]
    assert isinstance(failure_reason_breakdown, dict)
    assert int(failure_reason_breakdown.get("network_error", 0)) >= 1
    assert int(failure_reason_breakdown.get("route_apply_failed", 0)) >= 1


def test_expert_summon_rejects_failure_reason_for_non_failed_event(client: TestClient) -> None:
    response = client.post(
        "/api/v1/statistics/expert-summon/events",
        json={
            "event_type": "surface_viewed",
            "surface": "template_market",
            "failure_reason": "network_error",
        },
        headers={"Authorization": "Bearer local"},
    )
    assert response.status_code == 400


def test_expert_summon_rejects_non_dropped_count(client: TestClient) -> None:
    response = client.post(
        "/api/v1/statistics/expert-summon/events",
        json={
            "event_type": "summon_attempted",
            "surface": "template_market",
            "trigger": "template_card",
            "count": 2,
        },
        headers={"Authorization": "Bearer local"},
    )
    assert response.status_code == 400


def test_expert_summon_requires_trigger_for_summon_events(client: TestClient) -> None:
    response = client.post(
        "/api/v1/statistics/expert-summon/events",
        json={
            "event_type": "summon_attempted",
            "surface": "template_market",
        },
        headers={"Authorization": "Bearer local"},
    )
    assert response.status_code == 400
