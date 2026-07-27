from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api.statistics import wiki_evidence as wiki_evidence_module
from tests.support.minimal_app import build_minimal_app

app = build_minimal_app("notifications", preset="statistics")


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(autouse=True)
def _reset_alert_state_per_test() -> None:
    wiki_evidence_module._reset_wiki_evidence_alert_state_for_test()


def _list_wiki_alert_keys(client: TestClient) -> list[str]:
    response = client.get("/api/v1/notifications?limit=50", headers={"Authorization": "Bearer local"})
    assert response.status_code == 200
    payload = response.json()
    keys: list[str] = []
    for item in payload.get("items", []):
        if item.get("source") != "wiki_evidence":
            continue
        meta_data = item.get("meta_data") or {}
        alert_key = meta_data.get("alert_key")
        if isinstance(alert_key, str):
            keys.append(alert_key)
    return keys


def _get_summary(client: TestClient) -> dict[str, object]:
    response = client.get(
        "/api/v1/statistics/wiki-evidence/summary?days=365",
        headers={"Authorization": "Bearer local"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    return payload["data"]


def test_wiki_evidence_summary_accumulates_key_metrics(client: TestClient) -> None:
    before = _get_summary(client)

    events = [
        {"event_type": "evidence_surface", "surface": "settings", "context_key": "agent:default", "count": 4},
        {"event_type": "snippet_open", "surface": "settings", "context_key": "agent:default", "level": "L1"},
        {"event_type": "snippet_close", "surface": "settings", "context_key": "agent:default", "dwell_ms": 12000},
        {"event_type": "query_submitted", "surface": "settings", "context_key": "agent:default", "after_evidence": True},
        {"event_type": "dropped_report", "surface": "settings", "context_key": "agent:default", "count": 2},
    ]
    for event in events:
        response = client.post(
            "/api/v1/statistics/wiki-evidence/events",
            json=event,
            headers={"Authorization": "Bearer local"},
        )
        assert response.status_code == 200
        assert response.json()["success"] is True

    after = _get_summary(client)

    before_surface = int(before["evidence_surface_count"])
    after_surface = int(after["evidence_surface_count"])
    assert after_surface >= before_surface + 4

    before_open = int(before["snippet_open_count"])
    after_open = int(after["snippet_open_count"])
    assert after_open >= before_open + 1

    before_query = int(before["query_count"])
    after_query = int(after["query_count"])
    assert after_query >= before_query + 1

    before_requery = int(before["requery_count"])
    after_requery = int(after["requery_count"])
    assert after_requery >= before_requery + 1

    dwell_samples = int(after["verification_dwell_sample_count"])
    assert dwell_samples >= int(before["verification_dwell_sample_count"]) + 1
    assert float(after["verification_dwell_avg_ms"]) >= 0
    assert int(after["retention_days"]) >= 1
    assert int(after["dropped_event_count"]) >= int(before["dropped_event_count"]) + 2
    assert int(after["deep_verification_count"]) >= int(before["deep_verification_count"]) + 1
    assert float(after["deep_verification_rate"]) >= 0
    assert int(after["quick_bounce_count"]) >= int(before["quick_bounce_count"])
    assert float(after["quick_bounce_rate"]) >= 0

    by_surface = after["snippet_open_by_surface"]
    assert isinstance(by_surface, dict)
    assert "settings" in by_surface
    assert "chat" in by_surface

    by_level = after["snippet_open_by_level"]
    assert isinstance(by_level, dict)
    assert "L0" in by_level
    assert "L1" in by_level
    assert "L2" in by_level


def test_wiki_evidence_requires_dwell_for_snippet_close(client: TestClient) -> None:
    response = client.post(
        "/api/v1/statistics/wiki-evidence/events",
        json={"event_type": "snippet_close", "surface": "chat"},
        headers={"Authorization": "Bearer local"},
    )
    assert response.status_code == 400


def test_wiki_evidence_rejects_dwell_for_dropped_report(client: TestClient) -> None:
    response = client.post(
        "/api/v1/statistics/wiki-evidence/events",
        json={"event_type": "dropped_report", "surface": "chat", "dwell_ms": 1000},
        headers={"Authorization": "Bearer local"},
    )
    assert response.status_code == 400


def test_wiki_evidence_emits_drop_alert_with_dedup(client: TestClient) -> None:
    before_keys = _list_wiki_alert_keys(client)
    payload = {
        "event_type": "dropped_report",
        "surface": "chat",
        "context_key": "chat:alert",
        "count": wiki_evidence_module._ALERT_DROPPED_EVENT_THRESHOLD,
    }
    first = client.post("/api/v1/statistics/wiki-evidence/events", json=payload, headers={"Authorization": "Bearer local"})
    assert first.status_code == 200
    assert first.json()["success"] is True
    assert int(first.json()["data"]["alerts_emitted"]) >= 1
    after_first_keys = _list_wiki_alert_keys(client)
    assert len(after_first_keys) >= len(before_keys) + 1
    assert after_first_keys[0] == "wiki_evidence_dropped_events"

    second = client.post("/api/v1/statistics/wiki-evidence/events", json=payload, headers={"Authorization": "Bearer local"})
    assert second.status_code == 200
    assert second.json()["success"] is True
    assert int(second.json()["data"]["alerts_emitted"]) == 0
    after_second_keys = _list_wiki_alert_keys(client)
    assert len(after_second_keys) == len(after_first_keys)

    # Simulate process restart: in-memory cooldown is gone, DB cooldown dedup should still hold.
    wiki_evidence_module._reset_wiki_evidence_alert_state_for_test()
    third = client.post("/api/v1/statistics/wiki-evidence/events", json=payload, headers={"Authorization": "Bearer local"})
    assert third.status_code == 200
    assert third.json()["success"] is True
    assert int(third.json()["data"]["alerts_emitted"]) == 0
    after_third_keys = _list_wiki_alert_keys(client)
    assert len(after_third_keys) == len(after_second_keys)


def test_wiki_evidence_emits_low_deep_verification_alert(client: TestClient) -> None:
    before_keys = _list_wiki_alert_keys(client)
    open_resp = client.post(
        "/api/v1/statistics/wiki-evidence/events",
        json={
            "event_type": "snippet_open",
            "surface": "settings",
            "context_key": "agent:quality",
            "level": "L1",
            "count": wiki_evidence_module._ALERT_DEEP_VERIFICATION_MIN_OPEN_COUNT,
        },
        headers={"Authorization": "Bearer local"},
    )
    assert open_resp.status_code == 200
    alerts_emitted_total = int(open_resp.json()["data"]["alerts_emitted"])

    last_resp = None
    for _ in range(wiki_evidence_module._ALERT_DEEP_VERIFICATION_MIN_DWELL_SAMPLES):
        last_resp = client.post(
            "/api/v1/statistics/wiki-evidence/events",
            json={
                "event_type": "snippet_close",
                "surface": "settings",
                "context_key": "agent:quality",
                "dwell_ms": 1200,
            },
            headers={"Authorization": "Bearer local"},
        )
        assert last_resp.status_code == 200
        alerts_emitted_total += int(last_resp.json()["data"]["alerts_emitted"])

    assert last_resp is not None
    assert alerts_emitted_total >= 1
    after_keys = _list_wiki_alert_keys(client)
    assert len(after_keys) >= len(before_keys) + 1
    assert after_keys[0] == "wiki_evidence_low_deep_verification"


def test_wiki_evidence_skips_alert_evaluation_for_non_trigger_event(client: TestClient) -> None:
    seed_resp = client.post(
        "/api/v1/statistics/wiki-evidence/events",
        json={
            "event_type": "dropped_report",
            "surface": "chat",
            "context_key": "chat:seed",
            "count": wiki_evidence_module._ALERT_DROPPED_EVENT_THRESHOLD,
        },
        headers={"Authorization": "Bearer local"},
    )
    assert seed_resp.status_code == 200
    assert int(seed_resp.json()["data"]["alerts_emitted"]) >= 1

    non_trigger_resp = client.post(
        "/api/v1/statistics/wiki-evidence/events",
        json={
            "event_type": "query_submitted",
            "surface": "chat",
            "context_key": "chat:seed",
            "after_evidence": True,
        },
        headers={"Authorization": "Bearer local"},
    )
    assert non_trigger_resp.status_code == 200
    assert int(non_trigger_resp.json()["data"]["alerts_emitted"]) == 0
