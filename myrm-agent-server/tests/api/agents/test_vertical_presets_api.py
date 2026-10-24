"""API integration tests for Five Vertical Role Persona Presets and Sub-Bot Sandbox Tester (Item 64).

[INPUT]
- app.api.agents.vertical_presets_router.router
- app.services.agent.vertical_presets_service.VerticalPresetsService

[OUTPUT]
- Pytest assertions verifying presets listing, registration, sandbox test runs, and agent telemetry endpoints.

[POS]
- myrm-agent/myrm-agent-server/tests/api/agents/test_vertical_presets_api.py
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api.agents.vertical_presets_router import router as vertical_presets_router
from app.services.agent.vertical_presets_service import VerticalPresetsService


@pytest.fixture(autouse=True)
def reset_service_state() -> None:
    """Reset vertical presets catalog and trace store before each test."""
    VerticalPresetsService.clear()


@pytest.fixture
def client() -> TestClient:
    """TestClient fixture with vertical_presets_router attached."""
    app = FastAPI()
    app.include_router(vertical_presets_router)
    return TestClient(app)


def test_list_presets_api(client: TestClient) -> None:
    """Test querying built-in presets and filtering by category."""
    resp = client.get("/agents/vertical-presets")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data) == 5

    categories = {p["category"] for p in data}
    assert "life_admin" in categories
    assert "clipper" in categories

    resp_filtered = client.get("/agents/vertical-presets?category=office_manager")
    assert resp_filtered.status_code == 200
    filtered_data = resp_filtered.json()["data"]
    assert len(filtered_data) == 1
    assert filtered_data[0]["role_id"] == "office_manager"


def test_get_preset_api(client: TestClient) -> None:
    """Test getting single preset details and 404 for unknown role."""
    resp = client.get("/agents/vertical-presets/chief_of_staff")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["role_id"] == "chief_of_staff"
    assert data["display_name"] == "Chief of Staff Orchestrator"
    assert data["reasoning_effort"] == "high"

    resp_404 = client.get("/agents/vertical-presets/non_existent_role")
    assert resp_404.status_code == 404


def test_register_preset_api(client: TestClient) -> None:
    """Test registering a custom vertical persona preset."""
    payload = {
        "role_id": "legal_advisor",
        "category": "chief_of_staff",
        "display_name": "In-house Legal Advisor",
        "description": "Contracts, compliance, and terms of service auditor.",
        "persona_prompt": "You are a meticulous corporate lawyer.",
        "recommended_skills": ["contract_analysis"],
        "recommended_tools": ["doc_parser"],
        "reasoning_effort": "high",
        "typical_tasks": ["Review vendor agreements"],
    }
    resp = client.post("/agents/vertical-presets", json=payload)
    assert resp.status_code == 201
    data = resp.json()["data"]
    assert data["role_id"] == "legal_advisor"

    get_resp = client.get("/agents/vertical-presets/legal_advisor")
    assert get_resp.status_code == 200
    assert get_resp.json()["data"]["display_name"] == "In-house Legal Advisor"


def test_run_sandbox_test_api(client: TestClient) -> None:
    """Test running an isolated sandbox test for a specialist bot."""
    payload = {
        "role_id": "sales_team",
        "test_prompt": "Qualify inbound lead from enterprise Acme Corp with 500 seats.",
        "mock_inputs": {"company": "Acme Corp", "seats": "500"},
        "timeout_seconds": 15.0,
    }
    resp = client.post("/agents/vertical-presets/test-sandbox", json=payload)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["role_id"] == "sales_team"
    assert data["success"] is True
    assert "B2B Sales Development Rep" in data["output_text"]
    assert len(data["tool_calls_made"]) > 0
    assert data["execution_time_ms"] >= 0.0


def test_record_and_get_agent_trace_api(client: TestClient) -> None:
    """Test recording agent-to-agent communication steps and fetching full session trace."""
    step_payload = {
        "session_id": "sess-agent-flow-01",
        "root_agent_id": "chief_of_staff",
        "step": {
            "step_id": "step-001",
            "source_agent_id": "chief_of_staff",
            "target_agent_id": "sales_team",
            "action": "outreach_request",
            "payload_summary": "Draft email to CTO",
            "result_summary": "Draft ready",
            "duration_ms": 150.0,
            "timestamp": 1700000000.0,
        },
    }
    resp = client.post("/agents/vertical-presets/traces/record", json=step_payload)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["session_id"] == "sess-agent-flow-01"
    assert len(data["steps"]) == 1
    assert data["total_duration_ms"] == 150.0
    assert data["is_loop_detected"] is False

    get_resp = client.get("/agents/vertical-presets/traces/sess-agent-flow-01")
    assert get_resp.status_code == 200
    trace_data = get_resp.json()["data"]
    assert len(trace_data["steps"]) == 1


def test_agent_trace_loop_detection_api(client: TestClient) -> None:
    """Test ping-pong deadlocks trigger is_loop_detected=True in API response."""
    session_id = "sess-loop-check"
    pairs = [
        ("agent_a", "agent_b"),
        ("agent_b", "agent_a"),
        ("agent_a", "agent_b"),
        ("agent_b", "agent_a"),
    ]
    last_resp = None
    for idx, (src, dst) in enumerate(pairs):
        payload = {
            "session_id": session_id,
            "root_agent_id": "agent_a",
            "step": {
                "step_id": f"s-{idx}",
                "source_agent_id": src,
                "target_agent_id": dst,
                "action": "ping_pong",
                "payload_summary": f"msg {idx}",
                "result_summary": "",
                "duration_ms": 10.0,
                "timestamp": 1700000000.0 + idx,
            },
        }
        last_resp = client.post("/agents/vertical-presets/traces/record", json=payload)

    assert last_resp is not None
    assert last_resp.status_code == 200
    data = last_resp.json()["data"]
    assert data["is_loop_detected"] is True
