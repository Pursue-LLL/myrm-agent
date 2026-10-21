"""API integration tests for Clean-Code Assembly Pipeline and Architecture Dependency Linter (Item 62).

[INPUT]
- app.api.agents.clean_code_pipeline_router.router
- app.services.agent.clean_code_pipeline_service.CleanCodePipelineService

[OUTPUT]
- Pytest test cases validating 5-stage pipeline assembly, deliverable handovers,
  AST architecture linting, circular dependency detection, and DIP recommendations.

[POS]
- myrm-agent/myrm-agent-server/tests/api/agents/test_clean_code_pipeline_api.py
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api.agents.clean_code_pipeline_router import router as clean_code_pipeline_router
from app.services.agent.clean_code_pipeline_service import CleanCodePipelineService


@pytest.fixture(autouse=True)
def reset_service_state() -> None:
    """Clear in-memory pipeline state before each test."""
    CleanCodePipelineService.clear()


@pytest.fixture
def client() -> TestClient:
    """TestClient fixture with clean_code_pipeline_router attached."""
    app = FastAPI()
    app.include_router(clean_code_pipeline_router)
    return TestClient(app)


def test_create_and_get_task_api(client: TestClient) -> None:
    """Test creating a new clean-code assembly task and retrieving its initial state."""
    req_body = {
        "session_id": "session-clean-01",
        "title": "Payment Gateway Refactoring",
        "spec_prompt": "Design strict DIP domain models for multi-currency processing.",
    }
    resp = client.post("/agents/clean-code/tasks", json=req_body)
    assert resp.status_code == 200
    data = resp.json()["data"]

    task_id = data["task_id"]
    assert data["session_id"] == "session-clean-01"
    assert data["title"] == "Payment Gateway Refactoring"
    assert data["current_stage"] == "specifier"
    assert data["status"] == "running"
    assert data["stage_history"] == ["specifier"]

    # Get task by id
    get_resp = client.get(f"/agents/clean-code/tasks/{task_id}")
    assert get_resp.status_code == 200
    get_data = get_resp.json()["data"]
    assert get_data["task_id"] == task_id
    assert get_data["current_stage"] == "specifier"


def test_advance_stage_clean_flow_api(client: TestClient) -> None:
    """Test standard progression through all 5 pipeline stages."""
    create_resp = client.post(
        "/agents/clean-code/tasks",
        json={
            "session_id": "sess-flow-01",
            "title": "User Authentication Feature",
            "spec_prompt": "Initial Spec",
        },
    )
    task_id = create_resp.json()["data"]["task_id"]

    # 1. Specifier -> Coder
    adv1 = client.post(
        f"/agents/clean-code/tasks/{task_id}/advance",
        json={
            "artifact_title": "Interface Spec",
            "artifact_content": "Finalized formal interfaces.",
        },
    )
    assert adv1.status_code == 200
    assert adv1.json()["data"]["current_stage"] == "coder"
    assert adv1.json()["data"]["status"] == "running"

    # 2. Coder -> Cleaner
    adv2 = client.post(
        f"/agents/clean-code/tasks/{task_id}/advance",
        json={
            "artifact_title": "Core Implementation",
            "artifact_content": "Implemented core logic.",
        },
    )
    assert adv2.status_code == 200
    assert adv2.json()["data"]["current_stage"] == "cleaner"

    # 3. Cleaner -> Hardener
    adv3 = client.post(
        f"/agents/clean-code/tasks/{task_id}/advance",
        json={
            "artifact_title": "Refactored Clean Code",
            "artifact_content": "Removed duplicate code and eliminated bad smells.",
        },
    )
    assert adv3.status_code == 200
    assert adv3.json()["data"]["current_stage"] == "hardener"

    # 4. Hardener -> QA
    adv4 = client.post(
        f"/agents/clean-code/tasks/{task_id}/advance",
        json={
            "artifact_title": "Strict Type Safety and Hardening",
            "artifact_content": "Added strict type hints and error handling.",
        },
    )
    assert adv4.status_code == 200
    assert adv4.json()["data"]["current_stage"] == "qa"

    # 5. QA -> Completed
    adv5 = client.post(
        f"/agents/clean-code/tasks/{task_id}/advance",
        json={
            "artifact_title": "QA Test Verification",
            "artifact_content": "All unit tests and integration tests verified.",
        },
    )
    assert adv5.status_code == 200
    res_data = adv5.json()["data"]
    assert res_data["status"] == "completed"
    assert len(res_data["artifacts"]) == 5


def test_advance_stage_blocked_by_arch_violation_api(client: TestClient) -> None:
    """Test that submitting code with layer violations blocks the pipeline."""
    create_resp = client.post(
        "/agents/clean-code/tasks",
        json={
            "session_id": "sess-violation-01",
            "title": "Violating Feature",
            "spec_prompt": "Spec description",
        },
    )
    task_id = create_resp.json()["data"]["task_id"]

    # Provide source code where Domain layer illegal imports UI presentation layer
    violating_code = {
        "src/domain/account.py": "from src.ui.views import render_account\n\nclass Account:\n    pass\n",
    }

    adv = client.post(
        f"/agents/clean-code/tasks/{task_id}/advance",
        json={
            "artifact_title": "Spec with Architecture Violation",
            "artifact_content": "Spec completed.",
            "source_code_map": violating_code,
        },
    )
    assert adv.status_code == 200
    data = adv.json()["data"]
    assert data["status"] == "blocked"
    assert "arch_lint_report" in data["artifacts"]


def test_linter_check_standalone_api(client: TestClient) -> None:
    """Test standalone architecture AST check endpoint with circular dependency."""
    circular_code = {
        "src/services/billing.py": "import src.services.invoice\nclass Billing: pass\n",
        "src/services/invoice.py": "import src.services.billing\nclass Invoice: pass\n",
    }
    resp = client.post(
        "/agents/clean-code/linter/check",
        json={"source_code_map": circular_code},
    )
    assert resp.status_code == 200
    res = resp.json()["data"]
    assert res["is_valid"] is False
    assert res["scanned_files_count"] == 2
    types = [v["violation_type"] for v in res["violations"]]
    assert "circular_dependency" in types


def test_list_tasks_filtered_api(client: TestClient) -> None:
    """Test listing tasks and filtering by session_id."""
    client.post(
        "/agents/clean-code/tasks",
        json={"session_id": "sess-alpha", "title": "Task A", "spec_prompt": "Spec A"},
    )
    client.post(
        "/agents/clean-code/tasks",
        json={"session_id": "sess-beta", "title": "Task B", "spec_prompt": "Spec B"},
    )

    all_resp = client.get("/agents/clean-code/tasks")
    assert len(all_resp.json()["data"]) == 2

    filtered_resp = client.get("/agents/clean-code/tasks?session_id=sess-alpha")
    assert len(filtered_resp.json()["data"]) == 1
    assert filtered_resp.json()["data"][0]["session_id"] == "sess-alpha"
