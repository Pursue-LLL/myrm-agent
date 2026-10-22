"""API integration tests for External CLI Subagent Passthrough (Item 68).

[INPUT]
- app.api.agents.cli_passthrough_router.router
- app.services.agent.cli_passthrough_service.get_cli_passthrough_service

[OUTPUT]
- Pytest assertions verifying bundle discovery, privacy disclosures,
  headless non-interactive execution, workspace confinement, and egress accounting.

[POS]
- myrm-agent/myrm-agent-server/tests/api/agents/test_cli_passthrough_api.py
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api.agents.cli_passthrough_router import router as cli_passthrough_router
from app.services.agent.cli_passthrough_service import get_cli_passthrough_service


@pytest.fixture(autouse=True)
def reset_service_state() -> None:
    """Clear in-memory disclosures and audit log before each test."""
    service = get_cli_passthrough_service()
    service.reset()


@pytest.fixture
def client() -> TestClient:
    """TestClient fixture with cli_passthrough_router attached."""
    app = FastAPI()
    app.include_router(cli_passthrough_router)
    return TestClient(app)


def test_list_cli_bundles_api(client: TestClient) -> None:
    """Test discovering available external CLI bundles and BYOS status."""
    resp = client.get("/agents/cli-passthrough/bundles")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_bundles"] >= 3
    assert data["probe_installed_count"] >= 3
    bundle_ids = [b["bundle_id"] for b in data["bundles"]]
    assert "bundle-claude-code" in bundle_ids
    assert "bundle-codex-cli" in bundle_ids
    assert "bundle-cursor-cli" in bundle_ids


def test_create_and_acknowledge_privacy_disclosure_api(client: TestClient) -> None:
    """Test issuing and acknowledging a privacy disclosure."""
    payload = {
        "cli_type": "claude_code",
        "context_summary": "Refactor AST optimizer in src/compiler.py",
        "sensitivity_level": "medium",
    }
    resp = client.post("/agents/cli-passthrough/disclosures", json=payload)
    assert resp.status_code == 201
    disclosure = resp.json()
    assert disclosure["cli_type"] == "claude_code"
    assert disclosure["vendor_name"] == "Anthropic PBC"
    assert disclosure["user_acknowledged"] is False
    disc_id = disclosure["disclosure_id"]

    # Acknowledge disclosure
    ack_resp = client.post(
        "/agents/cli-passthrough/disclosures/acknowledge",
        json={"disclosure_id": disc_id, "user_acknowledged": True},
    )
    assert ack_resp.status_code == 200
    ack_data = ack_resp.json()
    assert ack_data["disclosure_id"] == disc_id
    assert ack_data["user_acknowledged"] is True


def test_execute_delegation_unacknowledged_fails_api(client: TestClient) -> None:
    """Test that executing task without acknowledged disclosure is blocked by privacy gate."""
    # Create unacknowledged disclosure
    disc_resp = client.post(
        "/agents/cli-passthrough/disclosures",
        json={
            "cli_type": "codex",
            "context_summary": "Unacknowledged task",
            "sensitivity_level": "high",
        },
    )
    disc_id = disc_resp.json()["disclosure_id"]

    exec_payload = {
        "task_id": "task-unack-01",
        "bundle_id": "bundle-codex-cli",
        "instruction": "Run code generation",
        "workspace_path": "/workspace/project",
        "disclosure_id": disc_id,
        "context_files": ["project/main.py"],
    }
    resp = client.post("/agents/cli-passthrough/execute", json=exec_payload)
    assert resp.status_code == 400
    assert "Privacy gate violation" in resp.json()["detail"]


def test_execute_delegation_workspace_violation_fails_api(client: TestClient) -> None:
    """Test that targeting paths outside allowed workspace root returns 403 Forbidden."""
    disc_resp = client.post(
        "/agents/cli-passthrough/disclosures",
        json={
            "cli_type": "claude_code",
            "context_summary": "Workspace boundary test",
            "sensitivity_level": "low",
        },
    )
    disc_id = disc_resp.json()["disclosure_id"]
    client.post(
        "/agents/cli-passthrough/disclosures/acknowledge",
        json={"disclosure_id": disc_id, "user_acknowledged": True},
    )

    exec_payload = {
        "task_id": "task-jailbreak-02",
        "bundle_id": "bundle-claude-code",
        "instruction": "Access root credentials",
        "workspace_path": "/etc/shadow",
        "disclosure_id": disc_id,
    }
    resp = client.post("/agents/cli-passthrough/execute", json=exec_payload)
    assert resp.status_code == 403
    assert "Workspace confinement violation" in resp.json()["detail"]


def test_execute_delegation_success_api(client: TestClient) -> None:
    """Test successful headless execution, diff extraction, and tamper-proof hash."""
    disc_resp = client.post(
        "/agents/cli-passthrough/disclosures",
        json={
            "cli_type": "cursor_cli",
            "context_summary": "Optimize SIMD vector normalization",
            "sensitivity_level": "low",
        },
    )
    disc_id = disc_resp.json()["disclosure_id"]
    client.post(
        "/agents/cli-passthrough/disclosures/acknowledge",
        json={"disclosure_id": disc_id, "user_acknowledged": True},
    )

    exec_payload = {
        "task_id": "task-success-03",
        "bundle_id": "bundle-cursor-cli",
        "instruction": "Implement Neon SIMD loop for Apple Silicon",
        "workspace_path": "/workspace/neon_bench",
        "disclosure_id": disc_id,
        "context_files": ["neon_bench/kernel.c"],
    }
    resp = client.post("/agents/cli-passthrough/execute", json=exec_payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["task_id"] == "task-success-03"
    assert data["bundle_id"] == "bundle-cursor-cli"
    assert data["exit_code"] == 0
    assert "--- a/neon_bench/kernel.c" in data["diff_output"]
    assert data["tokens_saved_estimate"] >= 120
    assert len(data["tamper_proof_audit_hash"]) == 64
    assert data["egress_accounting_id"].startswith("egress-")


def test_audit_log_and_reset_api(client: TestClient) -> None:
    """Test querying egress accounting records and clearing them."""
    # Execute one task
    disc_resp = client.post(
        "/agents/cli-passthrough/disclosures",
        json={
            "cli_type": "codex",
            "context_summary": "PR verification",
            "sensitivity_level": "medium",
        },
    )
    disc_id = disc_resp.json()["disclosure_id"]
    client.post(
        "/agents/cli-passthrough/disclosures/acknowledge",
        json={"disclosure_id": disc_id, "user_acknowledged": True},
    )

    client.post(
        "/agents/cli-passthrough/execute",
        json={
            "task_id": "task-audit-04",
            "bundle_id": "bundle-codex-cli",
            "instruction": "Verify PR changes",
            "workspace_path": "/workspace/repo",
            "disclosure_id": disc_id,
        },
    )

    # Query audit log
    audit_resp = client.get("/agents/cli-passthrough/audit-log")
    assert audit_resp.status_code == 200
    audit_data = audit_resp.json()
    assert audit_data["total_records"] == 1
    assert audit_data["records"][0]["task_id"] == "task-audit-04"

    # Reset
    del_resp = client.delete("/agents/cli-passthrough/reset")
    assert del_resp.status_code == 204

    audit_resp2 = client.get("/agents/cli-passthrough/audit-log")
    assert audit_resp2.json()["total_records"] == 0
