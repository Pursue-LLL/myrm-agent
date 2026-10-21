"""Unit tests for Per-Role Subagent Failure Restart & Redeploy Policy API endpoints (Item 35).

[INPUT]
- app.api.agents.failure_policy_router.router
- app.services.agent.failure_policy_service.FailurePolicyService

[OUTPUT]
- Pytest cases validating role policy registration, mid-task failure remediation evaluation,
  max_retries circuit breaking, counter resets, and timeline history.

[POS]
- myrm-agent/myrm-agent-server/tests/api/agents/test_failure_policy_api.py
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api.agents.failure_policy_router import (
    get_failure_policy_service,
)
from app.api.agents.failure_policy_router import (
    router as failure_policy_router,
)
from app.schemas.failure_policy import (
    FailureActionEnum,
    FailureTriggerReasonEnum,
)
from app.services.agent.failure_policy_service import FailurePolicyService


@pytest.fixture
def policy_service() -> FailurePolicyService:
    return FailurePolicyService()


@pytest.fixture
def policy_client(
    policy_service: FailurePolicyService,
) -> Generator[TestClient, None, None]:
    app = FastAPI()
    app.include_router(failure_policy_router)
    app.dependency_overrides[get_failure_policy_service] = lambda: policy_service
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_register_and_get_role_policy(policy_client: TestClient) -> None:
    chat_id = "chat_fail_test_01"

    # 1. Register researcher policy (allow_failure=True, skip)
    reg_resp = policy_client.post(
        f"/chats/{chat_id}/failure-policy/roles",
        json={
            "role_key": "researcher",
            "primary_action": "skip",
            "max_retries": 1,
            "allow_failure": True,
        },
    )
    assert reg_resp.status_code == 200
    reg_data = reg_resp.json()["data"]
    assert reg_data["role_key"] == "researcher"
    assert reg_data["primary_action"] == FailureActionEnum.SKIP.value
    assert reg_data["allow_failure"] is True

    # 2. Get specific role policy
    get_resp = policy_client.get(f"/chats/{chat_id}/failure-policy/roles/researcher")
    assert get_resp.status_code == 200
    assert get_resp.json()["data"]["role_key"] == "researcher"

    # 3. List all policies
    list_resp = policy_client.get(f"/chats/{chat_id}/failure-policy/roles")
    assert list_resp.status_code == 200
    policies = list_resp.json()["data"]["policies"]
    assert len(policies) >= 1
    assert any(p["role_key"] == "researcher" for p in policies)


def test_evaluate_remediation_and_circuit_break(policy_client: TestClient) -> None:
    chat_id = "chat_fail_test_02"
    task_id = "subtask_coder_01"

    # Register coder policy (restart_fresh, max_retries=2)
    policy_client.post(
        f"/chats/{chat_id}/failure-policy/roles",
        json={
            "role_key": "coder",
            "primary_action": "restart_fresh",
            "max_retries": 2,
            "allow_failure": False,
        },
    )

    # First crash: should decide RESTART_FRESH
    eval1 = policy_client.post(
        f"/chats/{chat_id}/failure-policy/evaluate",
        json={
            "task_id": task_id,
            "role_key": "coder",
            "trigger_reason": FailureTriggerReasonEnum.CRASH_ERROR.value,
            "error_message": "Process killed by OOM",
        },
    )
    assert eval1.status_code == 200
    d1 = eval1.json()["data"]
    assert d1["action"] == FailureActionEnum.RESTART_FRESH.value
    assert d1["attempt_number"] == 1
    assert d1["max_retries"] == 2

    # Second crash: should still decide RESTART_FRESH
    eval2 = policy_client.post(
        f"/chats/{chat_id}/failure-policy/evaluate",
        json={
            "task_id": task_id,
            "role_key": "coder",
            "trigger_reason": FailureTriggerReasonEnum.CRASH_ERROR.value,
            "error_message": "Segmentation fault",
        },
    )
    assert eval2.status_code == 200
    d2 = eval2.json()["data"]
    assert d2["action"] == FailureActionEnum.RESTART_FRESH.value
    assert d2["attempt_number"] == 2

    # Third crash: retry limit exceeded, should circuit break to ESCALATE_PARENT
    eval3 = policy_client.post(
        f"/chats/{chat_id}/failure-policy/evaluate",
        json={
            "task_id": task_id,
            "role_key": "coder",
            "trigger_reason": FailureTriggerReasonEnum.CRASH_ERROR.value,
            "error_message": "Persistent container panic",
        },
    )
    assert eval3.status_code == 200
    d3 = eval3.json()["data"]
    assert d3["action"] == FailureActionEnum.ESCALATE_PARENT.value
    assert "exceeded" in d3["rationale"].lower()


def test_redeploy_specs_and_history_timeline(policy_client: TestClient) -> None:
    chat_id = "chat_fail_test_03"
    task_id = "subtask_reviewer_01"

    # Register reviewer policy (redeploy_specs with downgrade)
    policy_client.post(
        f"/chats/{chat_id}/failure-policy/roles",
        json={
            "role_key": "reviewer",
            "primary_action": "redeploy_specs",
            "redeploy_model_tier_downgrade": True,
            "max_retries": 3,
        },
    )

    eval_resp = policy_client.post(
        f"/chats/{chat_id}/failure-policy/evaluate",
        json={
            "task_id": task_id,
            "role_key": "reviewer",
            "trigger_reason": FailureTriggerReasonEnum.OUTPUT_SPEC_MISMATCH.value,
            "error_message": "Output missed required schema sections",
        },
    )
    assert eval_resp.status_code == 200
    decision = eval_resp.json()["data"]
    assert decision["action"] == FailureActionEnum.REDEPLOY_SPECS.value

    # Check history timeline
    hist_resp = policy_client.get(f"/chats/{chat_id}/failure-policy/history?task_id={task_id}")
    assert hist_resp.status_code == 200
    history = hist_resp.json()["data"]
    assert len(history["history"]) == 1
    assert history["history"][0]["task_id"] == task_id


def test_reset_counter_and_session_cleanup(policy_client: TestClient) -> None:
    chat_id = "chat_fail_test_04"
    task_id = "subtask_worker_01"

    policy_client.post(
        f"/chats/{chat_id}/failure-policy/roles",
        json={
            "role_key": "worker",
            "primary_action": "restart_fresh",
            "max_retries": 1,
        },
    )

    # 1 fail
    policy_client.post(
        f"/chats/{chat_id}/failure-policy/evaluate",
        json={
            "task_id": task_id,
            "role_key": "worker",
            "trigger_reason": FailureTriggerReasonEnum.STUCK_TIMEOUT.value,
            "error_message": "Worker step timed out after 300s",
        },
    )

    # Reset counter
    reset_resp = policy_client.post(
        f"/chats/{chat_id}/failure-policy/tasks/{task_id}/reset-counter"
    )
    assert reset_resp.status_code == 200
    assert reset_resp.json()["data"]["reset"] is True

    # Next fail should start from attempt 1 again
    eval_again = policy_client.post(
        f"/chats/{chat_id}/failure-policy/evaluate",
        json={
            "task_id": task_id,
            "role_key": "worker",
            "trigger_reason": FailureTriggerReasonEnum.STUCK_TIMEOUT.value,
            "error_message": "Worker step timed out after 300s",
        },
    )
    assert eval_again.json()["data"]["attempt_number"] == 1
    assert eval_again.json()["data"]["action"] == FailureActionEnum.RESTART_FRESH.value

    # Session purge
    purge_resp = policy_client.delete(f"/chats/{chat_id}/failure-policy")
    assert purge_resp.status_code == 200
    assert purge_resp.json()["data"]["reset"] is True

    # After purge, policies list is empty
    empty_list = policy_client.get(f"/chats/{chat_id}/failure-policy/roles")
    assert empty_list.json()["data"]["policies"] == []
