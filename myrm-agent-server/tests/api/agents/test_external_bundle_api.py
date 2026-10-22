"""API integration tests for Heterogeneous External Agent Adapter and Subagent Bundle Manager (Item 75).

[INPUT]
- app.api.agents.external_bundle_router.router
- app.services.agent.external_bundle_service.ExternalBundleService

[OUTPUT]
- Pytest assertions verifying external agent bundle discovery, executable binary probing,
  sandbox directory boundary protection (403 on traversal), unlocked parallel batch dispatch
  (simultaneous execution of multiple Codex/Claude Code instances), and manual termination.

[POS]
- myrm-agent/myrm-agent-server/tests/api/agents/test_external_bundle_api.py
"""

from __future__ import annotations

import tempfile
from typing import Generator

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api.agents.external_bundle_router import router as external_bundle_router
from app.services.agent.external_bundle_service import ExternalBundleService


@pytest.fixture
def tmp_sandbox_dir() -> Generator[str, None, None]:
    """Provide isolated temporary directory for test sandbox."""
    with tempfile.TemporaryDirectory() as d:
        yield d


@pytest.fixture
def client(tmp_sandbox_dir: str) -> Generator[TestClient, None, None]:
    """TestClient fixture with isolated ExternalBundleService and router attached."""
    ExternalBundleService.reset_instance()
    service = ExternalBundleService.get_instance()
    service._default_workspace_base = tmp_sandbox_dir

    app = FastAPI()
    app.include_router(external_bundle_router)
    with TestClient(app) as test_client:
        yield test_client

    ExternalBundleService.reset_instance()


def test_list_bundles_and_probe_api(client: TestClient) -> None:
    """Test listing built-in external bundles and querying single bundle specification."""
    # List bundles
    resp = client.get("/agents/external-bundles/bundles")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_bundles"] >= 3
    bundle_ids = {b["bundle_id"] for b in data["bundles"]}
    assert "subagent-claude-code" in bundle_ids
    assert "subagent-codex" in bundle_ids
    assert "subagent-gemini-cli" in bundle_ids

    # Get single bundle
    codex_resp = client.get("/agents/external-bundles/bundles/subagent-codex")
    assert codex_resp.status_code == 200
    codex_data = codex_resp.json()
    assert codex_data["binary_name"] == "codex"
    assert "unit_testing" in codex_data["capabilities"]

    # Probe bundle
    probe_resp = client.post("/agents/external-bundles/bundles/subagent-codex/probe")
    assert probe_resp.status_code == 200
    assert probe_resp.json()["bundle_id"] == "subagent-codex"

    # Nonexistent bundle 404
    bad_resp = client.get("/agents/external-bundles/bundles/unknown-bundle-404")
    assert bad_resp.status_code == 404


def test_sandbox_directory_traversal_rejection_api(
    client: TestClient,
    tmp_sandbox_dir: str,
) -> None:
    """Ensure subagent dispatch outside allowed workspace root is rejected with HTTP 403."""
    session_id = "test-session-security"

    payload = {
        "task": {
            "bundle_id": "subagent-codex",
            "role_label": "escapist",
            "task_prompt": "Read root files",
            "target_subdir": "../../etc/sensitive",
        },
        "workspace_root": f"{tmp_sandbox_dir}/workspace",
    }

    resp = client.post(
        f"/agents/external-bundles/sessions/{session_id}/dispatch-single",
        json=payload,
    )
    assert resp.status_code == 403
    assert "Security Violation" in resp.json()["detail"]


def test_single_and_batch_parallel_dispatch_api(
    client: TestClient,
    tmp_sandbox_dir: str,
) -> None:
    """Ensure multiple instances of the same bundle (Codex) can be dispatched concurrently."""
    session_id = "test-session-batch"
    ws = f"{tmp_sandbox_dir}/{session_id}"

    # Batch dispatch: 2 Codex instances + 1 Claude Code instance
    batch_payload = {
        "tasks": [
            {
                "bundle_id": "subagent-codex",
                "role_label": "frontend-coder",
                "task_prompt": "Implement Vue/React components",
                "target_subdir": "frontend",
            },
            {
                "bundle_id": "subagent-codex",
                "role_label": "backend-coder",
                "task_prompt": "Implement SQLAlchemy models",
                "target_subdir": "backend",
            },
            {
                "bundle_id": "subagent-claude-code",
                "role_label": "qa-reviewer",
                "task_prompt": "Review diffs and run type checks",
                "target_subdir": "",
            },
        ],
        "workspace_root": ws,
    }

    resp = client.post(
        f"/agents/external-bundles/sessions/{session_id}/dispatch-batch",
        json=batch_payload,
    )
    assert resp.status_code == 201
    batch_data = resp.json()
    assert batch_data["total_dispatched"] == 3
    instances = batch_data["dispatched_instances"]
    assert len(instances) == 3

    # Query instance list for session
    list_resp = client.get(f"/agents/external-bundles/sessions/{session_id}/instances")
    assert list_resp.status_code == 200
    list_data = list_resp.json()
    assert len(list_data) == 3

    # Query single instance
    first_id = instances[0]["instance_id"]
    inst_resp = client.get(f"/agents/external-bundles/sessions/{session_id}/instances/{first_id}")
    assert inst_resp.status_code == 200
    assert inst_resp.json()["instance_id"] == first_id


def test_terminate_instance_api(
    client: TestClient,
    tmp_sandbox_dir: str,
) -> None:
    """Test manual termination of an active external subagent instance."""
    session_id = "test-session-term"
    ws = f"{tmp_sandbox_dir}/{session_id}"

    # Dispatch single
    payload = {
        "task": {
            "bundle_id": "subagent-codex",
            "role_label": "stoppable-worker",
            "task_prompt": "Execute long process",
        },
        "workspace_root": ws,
    }
    dispatch_resp = client.post(
        f"/agents/external-bundles/sessions/{session_id}/dispatch-single",
        json=payload,
    )
    assert dispatch_resp.status_code == 201
    instance_id = dispatch_resp.json()["instance_id"]

    # Terminate instance
    term_resp = client.post(
        f"/agents/external-bundles/sessions/{session_id}/instances/{instance_id}/terminate",
        json={"reason": "cancelled_by_operator"},
    )
    assert term_resp.status_code == 200
    term_data = term_resp.json()
    assert term_data["terminated"] is True
    assert term_data["status"] == "terminated"
    assert "cancelled_by_operator" in str(term_data["error"])
