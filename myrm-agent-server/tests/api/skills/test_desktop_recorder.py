"""Integration tests for Desktop Recorder API endpoints."""

from fastapi.testclient import TestClient


def test_desktop_recorder_lifecycle_and_plan_compile(client: TestClient) -> None:
    session_id = "test-session-integration-001"

    # 1. Start recording
    start_resp = client.post(
        "/api/v1/skills/desktop-recorder/start",
        json={"session_id": session_id, "app_scope": "all"},
    )
    assert start_resp.status_code == 200
    start_data = start_resp.json()
    assert start_data["session_id"] == session_id
    assert start_data["status"] == "recording"

    # 2. Append events
    ev1 = {
        "session_id": session_id,
        "seq": 1,
        "action": "app_switch",
        "app_name": "Microsoft Excel",
        "window_title": "Q3_Report.xlsx",
    }
    client.post("/api/v1/skills/desktop-recorder/event", json=ev1)

    ev2 = {
        "session_id": session_id,
        "seq": 2,
        "action": "click",
        "app_name": "Microsoft Excel",
        "element_title": "Export Button",
        "window_title": "Q3_Report.xlsx",
    }
    client.post("/api/v1/skills/desktop-recorder/event", json=ev2)

    ev3 = {
        "session_id": session_id,
        "seq": 3,
        "action": "type",
        "app_name": "Chrome Browser",
        "element_title": "Search Input",
        "value": "ORDER-99120",
        "window_title": "Customs Portal",
    }
    client.post("/api/v1/skills/desktop-recorder/event", json=ev3)

    # 3. Stop recording
    stop_resp = client.post(
        "/api/v1/skills/desktop-recorder/stop",
        json={"session_id": session_id},
    )
    assert stop_resp.status_code == 200
    stop_data = stop_resp.json()
    assert stop_data["status"] == "stopped"
    assert stop_data["event_count"] == 3

    # 4. Analyze Plan (Intent + Ordered Steps)
    analyze_resp = client.post(
        "/api/v1/skills/desktop-recorder/analyze-plan",
        json={
            "session_id": session_id,
            "skill_name": "Excel To Customs Sync",
            "intent_hint": "Automate Excel data sync to Customs",
        },
    )
    assert analyze_resp.status_code == 200
    analyze_data = analyze_resp.json()
    plan = analyze_data["plan"]
    assert plan["name"] == "Excel To Customs Sync"
    assert len(plan["steps"]) == 3
    assert len(analyze_data["validation_errors"]) == 0
    assert "input_val_3" in plan["variables"]

    # 5. Compile Plan into Markdown
    compile_resp = client.post(
        "/api/v1/skills/desktop-recorder/compile-plan",
        json={"plan": plan},
    )
    assert compile_resp.status_code == 200
    compile_data = compile_resp.json()
    md = compile_data["markdown_content"]
    assert "name: excel-to-customs-sync" in md
    assert "## Parameters & Variables" in md
    assert "## Execution Steps" in md
    assert "### 1. Switch to application Microsoft Excel" in md
    assert "### 2. Interact with Export Button in Microsoft Excel" in md
    assert "### 3. Input value into Search Input in Chrome Browser" in md
