"""Tests for Desktop Workflow Skill Recorder REST API."""

from __future__ import annotations

import time

from fastapi.testclient import TestClient


def test_desktop_recorder_api_lifecycle(client: TestClient) -> None:
    session_id = f"test_session_{int(time.time())}"

    # 1. Start recording
    start_res = client.post(
        "/api/v1/skills/desktop-recorder/start",
        json={"session_id": session_id, "app_scope": "all"},
    )
    assert start_res.status_code == 200
    start_data = start_res.json()
    assert start_data["session_id"] == session_id
    assert start_data["status"] == "recording"

    # 2. Append events
    event_res1 = client.post(
        "/api/v1/skills/desktop-recorder/event",
        json={
            "session_id": session_id,
            "seq": 1,
            "action": "click",
            "app_name": "FinanceApp",
            "dref_id": "@dref:10",
            "element_title": "Monthly Reconciliation",
        },
    )
    assert event_res1.status_code == 200
    assert event_res1.json()["recorded_count"] == 1

    event_res2 = client.post(
        "/api/v1/skills/desktop-recorder/event",
        json={
            "session_id": session_id,
            "seq": 2,
            "action": "type",
            "app_name": "Terminal",
            "value": "python reconcile.py --date 2026-08-20",
        },
    )
    assert event_res2.status_code == 200
    assert event_res2.json()["recorded_count"] == 2

    # 3. Get session state
    session_res = client.get(f"/api/v1/skills/desktop-recorder/session/{session_id}")
    assert session_res.status_code == 200
    assert session_res.json()["events_count"] == 2

    # 4. Stop recording
    stop_res = client.post(
        "/api/v1/skills/desktop-recorder/stop",
        json={"session_id": session_id},
    )
    assert stop_res.status_code == 200
    assert stop_res.json()["status"] == "stopped"

    # 5. Synthesize skill
    synth_res = client.post(
        "/api/v1/skills/desktop-recorder/synthesize",
        json={
            "session_id": session_id,
            "skill_name": "finance_reconcile_workflow",
            "description": "Automated reconciliation for monthly reports",
        },
    )
    assert synth_res.status_code == 200
    draft = synth_res.json()
    assert draft["skill_name"] == "finance_reconcile_workflow"
    assert len(draft["steps"]) >= 2
    assert "name: finance_reconcile_workflow" in draft["markdown_content"]
