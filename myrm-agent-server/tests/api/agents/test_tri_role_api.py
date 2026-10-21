"""Unit tests for Tri-Role Separation Pipeline & Artifact Handoff API (Item 40).

[INPUT]
- app.api.agents.tri_role_router.router
- app.services.agent.tri_role_service.TriRoleService

[OUTPUT]
- Pytest test cases verifying cognitive separation stages, independent evaluator verdicts,
  acceptance criteria validation, and cross-session artifact handoff manifests.

[POS]
- myrm-agent/myrm-agent-server/tests/api/agents/test_tri_role_api.py
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api.agents.tri_role_router import (
    get_tri_role_service,
)
from app.api.agents.tri_role_router import (
    router as tri_role_router,
)
from app.services.agent.tri_role_service import (
    TriRoleService,
)


@pytest.fixture
def tri_service() -> TriRoleService:
    return TriRoleService()


@pytest.fixture
def client(tri_service: TriRoleService) -> Generator[TestClient, None, None]:
    app = FastAPI()
    app.include_router(tri_role_router)
    app.dependency_overrides[get_tri_role_service] = lambda: tri_service
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_create_and_get_session_api(client: TestClient) -> None:
    chat_id = "chat-tri-1"
    resp = client.post(
        f"/chats/{chat_id}/tri-role/sessions",
        json={
            "session_id": chat_id,
            "task_description": "Implement User Authentication",
            "stage_names": ["Planning & Spec", "Code Generation", "Security Verification"],
        },
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["session_id"] == chat_id
    assert len(data["stages"]) == 3
    assert data["stages"][0]["status"] == "planned"
    assert data["current_stage_index"] == 0

    # Test GET
    get_resp = client.get(f"/chats/{chat_id}/tri-role/sessions")
    assert get_resp.status_code == 200
    get_data = get_resp.json()["data"]
    assert get_data["session_id"] == chat_id


def test_full_pipeline_stage_flow_api(client: TestClient) -> None:
    chat_id = "chat-tri-flow"
    create_resp = client.post(
        f"/chats/{chat_id}/tri-role/sessions",
        json={
            "session_id": chat_id,
            "task_description": "Database Migration",
            "stage_names": ["Schema Design"],
        },
    )
    assert create_resp.status_code == 200
    stage_id = create_resp.json()["data"]["stages"][0]["stage_id"]

    # 1. Planner submits plan
    plan_resp = client.post(
        f"/chats/{chat_id}/tri-role/stages/{stage_id}/plan",
        json={
            "planner_output": "Designed schema for accounts table.",
            "criteria": [
                {
                    "criterion_id": "c_users",
                    "description": "Users table has email index",
                    "assertion_rule": "index_exists('users_email_idx')",
                    "is_satisfied": False,
                }
            ],
        },
    )
    assert plan_resp.status_code == 200
    assert plan_resp.json()["data"]["status"] == "generating"

    # 2. Generator submits code
    gen_resp = client.post(
        f"/chats/{chat_id}/tri-role/stages/{stage_id}/generate",
        json={
            "generator_output": "Generated migration script 001_accounts.py",
            "produced_files": ["alembic/versions/001_accounts.py"],
        },
    )
    assert gen_resp.status_code == 200
    assert gen_resp.json()["data"]["status"] == "evaluating"

    # 3. Evaluator evaluates stage (accepted)
    eval_resp = client.post(
        f"/chats/{chat_id}/tri-role/stages/{stage_id}/evaluate",
        json={
            "evaluator_notes": "Migration successfully applied in test DB and index confirmed.",
            "criteria_evaluations": {"c_users": True},
            "min_pass_rate": 1.0,
        },
    )
    assert eval_resp.status_code == 200
    verdict = eval_resp.json()["data"]
    assert verdict["is_accepted"] is True
    assert verdict["score"] == 1.0

    # 4. Advance stage
    adv_resp = client.post(f"/chats/{chat_id}/tri-role/advance")
    assert adv_resp.status_code == 200
    assert adv_resp.json()["data"]["is_completed"] is True


def test_evaluate_rejection_api(client: TestClient) -> None:
    chat_id = "chat-tri-reject"
    create_resp = client.post(
        f"/chats/{chat_id}/tri-role/sessions",
        json={
            "session_id": chat_id,
            "task_description": "Payment Integration",
            "stage_names": ["Stripe Webhook"],
        },
    )
    stage_id = create_resp.json()["data"]["stages"][0]["stage_id"]

    client.post(
        f"/chats/{chat_id}/tri-role/stages/{stage_id}/plan",
        json={
            "planner_output": "Handle Stripe webhooks",
            "criteria": [
                {
                    "criterion_id": "c_sig",
                    "description": "Webhook signature verification",
                    "assertion_rule": "verify_signature() == True",
                    "is_satisfied": False,
                }
            ],
        },
    )
    client.post(
        f"/chats/{chat_id}/tri-role/stages/{stage_id}/generate",
        json={
            "generator_output": "Naive handler without signature check",
            "produced_files": ["webhook.py"],
        },
    )

    eval_resp = client.post(
        f"/chats/{chat_id}/tri-role/stages/{stage_id}/evaluate",
        json={
            "evaluator_notes": "Signature check is missing or bypassed.",
            "criteria_evaluations": {"c_sig": False},
            "min_pass_rate": 1.0,
        },
    )
    assert eval_resp.status_code == 200
    assert eval_resp.json()["data"]["is_accepted"] is False

    # Verify stage is rejected
    sess_resp = client.get(f"/chats/{chat_id}/tri-role/sessions")
    assert sess_resp.json()["data"]["stages"][0]["status"] == "rejected"


def test_manifest_export_and_restore_api(client: TestClient) -> None:
    origin_chat = "chat-origin"
    create_resp = client.post(
        f"/chats/{origin_chat}/tri-role/sessions",
        json={
            "session_id": origin_chat,
            "task_description": "Build Engine Core",
            "stage_names": ["Core Engine"],
        },
    )
    stage_id = create_resp.json()["data"]["stages"][0]["stage_id"]

    client.post(
        f"/chats/{origin_chat}/tri-role/stages/{stage_id}/plan",
        json={
            "planner_output": "Plan Core",
            "criteria": [
                {
                    "criterion_id": "c_core",
                    "description": "Core is deterministic",
                    "assertion_rule": "test_core() == PASS",
                    "is_satisfied": False,
                }
            ],
        },
    )
    client.post(
        f"/chats/{origin_chat}/tri-role/stages/{stage_id}/generate",
        json={
            "generator_output": "Core implemented",
            "produced_files": ["core.py"],
        },
    )
    client.post(
        f"/chats/{origin_chat}/tri-role/stages/{stage_id}/evaluate",
        json={
            "evaluator_notes": "All verified",
            "criteria_evaluations": {"c_core": True},
        },
    )

    # Export manifest
    export_resp = client.get(f"/chats/{origin_chat}/tri-role/manifest")
    assert export_resp.status_code == 200
    manifest_data = export_resp.json()["data"]
    assert manifest_data["session_id"] == origin_chat
    assert manifest_data["produced_files"] == ["core.py"]

    # Restore in new session
    new_chat = "chat-restored"
    restore_resp = client.post(
        f"/chats/{new_chat}/tri-role/manifest/restore",
        json={
            "new_session_id": new_chat,
            "task_description": "Extend Core with Extensions",
            "manifest": manifest_data,
            "subsequent_stage_names": ["Extension Pack 1"],
        },
    )
    assert restore_resp.status_code == 200
    restored_session = restore_resp.json()["data"]
    assert restored_session["session_id"] == new_chat
    assert len(restored_session["stages"]) == 2
    assert restored_session["stages"][0]["status"] == "accepted"
    assert restored_session["current_stage_index"] == 1
