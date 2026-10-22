"""Unit tests for Hermes Fabric remote dispatch and durable journals API endpoints.

[INPUT]
- app.api.agents.durable_dispatch_router.router
- app.services.agent.durable_dispatch_service.DurableDispatchService

[OUTPUT]
- Pytest test cases verifying remote dispatch preparation, fail-closed pre-start policy revalidation, bounded evidence admission, journal querying, and idempotent recovery planning.

[POS]
myrm-agent/myrm-agent-server/tests/api/agents/test_durable_dispatch_api.py
"""

from __future__ import annotations

import time
from collections.abc import Generator

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api.agents.durable_dispatch_router import (
    get_durable_dispatch_service,
)
from app.api.agents.durable_dispatch_router import (
    router as durable_dispatch_router,
)
from app.services.agent.durable_dispatch_service import DurableDispatchService


@pytest.fixture
def mock_durable_service() -> DurableDispatchService:
    return DurableDispatchService()


@pytest.fixture
def durable_client(
    mock_durable_service: DurableDispatchService,
) -> Generator[TestClient, None, None]:
    app = FastAPI()
    app.include_router(durable_dispatch_router)
    app.dependency_overrides[get_durable_dispatch_service] = lambda: mock_durable_service
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_prepare_dispatch_api(durable_client: TestClient) -> None:
    chat_id = "chat_test_dispatch_01"
    contract_payload = {
        "dispatch_id": "dsp_api_001",
        "task_name": "compile_rust_module",
        "target_peer_id": "sandbox_node_wasm",
        "coordinator_principal_id": "coord_primary",
        "max_budget_tokens": 30000,
        "expires_at": time.time() + 600.0,
        "required_policies": ["sandbox_isolation", "network_whitelist"],
    }

    resp = durable_client.post(
        f"/chats/{chat_id}/remote-dispatch/prepare",
        json=contract_payload,
        headers={"X-Coordinator-Token": "valid_coordinator_token"},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["dispatch_id"] == "dsp_api_001"
    assert data["acknowledged_seq"] == 1
    assert data["peer_status"] == "accepted"


def test_revalidate_policy_api(durable_client: TestClient) -> None:
    chat_id = "chat_test_dispatch_02"
    contract_payload = {
        "dispatch_id": "dsp_api_002",
        "task_name": "run_linter",
        "target_peer_id": "sandbox_node_py",
        "expires_at": time.time() + 600.0,
        "required_policies": ["sandbox_isolation", "credential_validity"],
    }
    durable_client.post(f"/chats/{chat_id}/remote-dispatch/prepare", json=contract_payload)

    # 1. Incomplete policies -> fail closed
    resp_fail = durable_client.post(
        f"/chats/{chat_id}/remote-dispatch/dsp_api_002/revalidate-policy",
        json={"active_policies": {"sandbox_isolation": True, "credential_validity": False}},
    )
    assert resp_fail.status_code == 200
    assert resp_fail.json()["data"]["passed"] is False

    # 2. All policies valid -> pass
    resp_pass = durable_client.post(
        f"/chats/{chat_id}/remote-dispatch/dsp_api_002/revalidate-policy",
        json={"active_policies": {"sandbox_isolation": True, "credential_validity": True}},
    )
    assert resp_pass.status_code == 200
    assert resp_pass.json()["data"]["passed"] is True


def test_bounded_evidence_and_journal_api(durable_client: TestClient) -> None:
    chat_id = "chat_test_dispatch_03"
    contract_payload = {
        "dispatch_id": "dsp_api_003",
        "task_name": "run_test_suite",
        "target_peer_id": "sandbox_node_ci",
        "expires_at": time.time() + 600.0,
    }
    durable_client.post(f"/chats/{chat_id}/remote-dispatch/prepare", json=contract_payload)

    # 1. Submit normal evidence (2KB) -> admitted
    valid_evidence = {
        "evidence_type": "unit_test_log",
        "size_bytes": 2048,
        "content_digest": "sha256_mock_valid_log",
        "description": "5 passed tests",
    }
    resp_admitted = durable_client.post(
        f"/chats/{chat_id}/remote-dispatch/dsp_api_003/evidence",
        json=valid_evidence,
    )
    assert resp_admitted.status_code == 200
    assert resp_admitted.json()["data"]["admitted"] is True

    # 2. Submit oversized evidence (100KB) -> rejected by bounds
    oversized_evidence = {
        "evidence_type": "core_dump",
        "size_bytes": 100 * 1024,
        "content_digest": "sha256_mock_huge",
    }
    resp_rejected = durable_client.post(
        f"/chats/{chat_id}/remote-dispatch/dsp_api_003/evidence",
        json=oversized_evidence,
    )
    assert resp_rejected.status_code == 200
    assert resp_rejected.json()["data"]["admitted"] is False

    # 3. Retrieve journal entries
    resp_journal = durable_client.get(f"/chats/{chat_id}/remote-dispatch/dsp_api_003/journal")
    assert resp_journal.status_code == 200
    journal_list = resp_journal.json()["data"]
    assert len(journal_list) >= 3
    assert journal_list[0]["seq"] == 1
    assert journal_list[0]["entry_type"] == "dispatch_init"


def test_recovery_plan_api(durable_client: TestClient) -> None:
    chat_id = "chat_test_dispatch_04"
    contract_payload = {
        "dispatch_id": "dsp_api_004",
        "task_name": "build_frontend_bundle",
        "target_peer_id": "sandbox_node_node",
        "expires_at": time.time() + 600.0,
        "required_policies": ["sandbox_isolation"],
    }
    durable_client.post(f"/chats/{chat_id}/remote-dispatch/prepare", json=contract_payload)
    durable_client.post(
        f"/chats/{chat_id}/remote-dispatch/dsp_api_004/revalidate-policy",
        json={"active_policies": {"sandbox_isolation": True}},
    )

    # Compute crash recovery plan
    resp_recovery = durable_client.post(f"/chats/{chat_id}/remote-dispatch/dsp_api_004/recovery")
    assert resp_recovery.status_code == 200
    plan = resp_recovery.json()["data"]
    assert plan["dispatch_id"] == "dsp_api_004"
    assert plan["can_resume"] is True
    assert plan["resume_action"] == "idempotent_continue_execution"
