"""
[POS] tests/api/security/test_readonly_research_sandbox_endpoints.py
[INPUT] app.api.security.readonly_research_sandbox_router, app.services.security.readonly_research_sandbox_service
[OUTPUT] endpoint tests

API endpoint tests for Read-Only Autonomous Research Lease & Immutable Snapshot Sandbox Suite.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.security.readonly_research_sandbox_router import (
    router as readonly_research_sandbox_router,
)
from app.services.security.readonly_research_sandbox_service import (
    ReadOnlyResearchSandboxService,
    get_readonly_research_sandbox_service,
)


@pytest.fixture
def client() -> TestClient:
    test_service = ReadOnlyResearchSandboxService()
    app = FastAPI()
    app.include_router(readonly_research_sandbox_router)
    app.dependency_overrides[get_readonly_research_sandbox_service] = (
        lambda: test_service
    )
    return TestClient(app)


def test_lease_and_tool_evaluation_endpoints(client: TestClient) -> None:
    """Test POST/GET /readonly-research/lease and POST /evaluate-tool."""
    session_id = "sess-api-ro-01"

    # 1. Grant lease
    grant_res = client.post(
        "/readonly-research/lease",
        json={
            "session_id": session_id,
            "research_mode": "AUTONOMOUS_RESEARCH",
            "ttl_seconds": 3600.0,
        },
    )
    assert grant_res.status_code == 201
    lease = grant_res.json()
    assert lease["status"] == "ACTIVE"
    assert lease["research_mode"] == "AUTONOMOUS_RESEARCH"

    # 2. Get lease
    get_res = client.get(f"/readonly-research/lease/{session_id}")
    assert get_res.status_code == 200
    assert get_res.json()["lease_id"] == lease["lease_id"]

    # 3. Evaluate tool: read allowed
    eval_r = client.post(
        "/readonly-research/evaluate-tool",
        json={"session_id": session_id, "tool_name": "read_file"},
    )
    assert eval_r.status_code == 200
    assert eval_r.json()["is_allowed"] is True

    # 4. Evaluate tool: write blocked
    eval_w = client.post(
        "/readonly-research/evaluate-tool",
        json={"session_id": session_id, "tool_name": "write_file"},
    )
    assert eval_w.status_code == 200
    assert eval_w.json()["is_allowed"] is False
    assert "physically stripped" in eval_w.json()["explanation"]

    # 5. Revoke lease
    rev_res = client.post(f"/readonly-research/lease/{session_id}/revoke")
    assert rev_res.status_code == 200
    assert rev_res.json()["status"] == "REVOKED"


def test_snapshot_and_purity_endpoints(client: TestClient) -> None:
    """Test POST /readonly-research/snapshot and POST /verify-purity."""
    session_id = "sess-api-snap-01"
    files = {"index.html": "<html></html>", "style.css": "body{}"}

    # 1. Take snapshot
    snap_res = client.post(
        "/readonly-research/snapshot",
        json={"session_id": session_id, "baseline_files": files},
    )
    assert snap_res.status_code == 201
    s_data = snap_res.json()
    assert s_data["tracked_files_count"] == 2
    assert len(s_data["root_digest"]) == 64

    # 2. Verify purity: pristine
    pure_res = client.post(
        "/readonly-research/verify-purity",
        json={"session_id": session_id, "current_files": files},
    )
    assert pure_res.status_code == 200
    assert pure_res.json()["is_pure"] is True

    # 3. Verify purity: polluted
    polluted = dict(files)
    polluted["extra.log"] = "polluted file"
    fail_res = client.post(
        "/readonly-research/verify-purity",
        json={"session_id": session_id, "current_files": polluted},
    )
    assert fail_res.status_code == 200
    assert fail_res.json()["is_pure"] is False


def test_ephemeral_file_and_badge_endpoints(client: TestClient) -> None:
    """Test staging transient CoW files, purging overlay, and checking shield badge."""
    session_id = "sess-api-badge-01"

    # 1. Write ephemeral file
    f_res = client.post(
        "/readonly-research/ephemeral-file",
        json={
            "session_id": session_id,
            "virtual_path": "research/summary.md",
            "content": "# Research Report",
        },
    )
    assert f_res.status_code == 201
    assert f_res.json()["virtual_path"] == "research/summary.md"

    # 2. List ephemeral files
    list_res = client.get(f"/readonly-research/ephemeral-files/{session_id}")
    assert list_res.status_code == 200
    assert len(list_res.json()) == 1

    # 3. Get shield badge
    badge_res = client.get(f"/readonly-research/badge/{session_id}")
    assert badge_res.status_code == 200
    b_data = badge_res.json()
    assert b_data["cow_overlay_active"] is True

    # 4. Purge overlay
    purge_res = client.post(f"/readonly-research/purge-overlay/{session_id}")
    assert purge_res.status_code == 200
    assert purge_res.json()["purged_files_count"] == 1

    # 5. Metrics
    metrics_res = client.get("/readonly-research/metrics")
    assert metrics_res.status_code == 200
    assert "total_leases_granted" in metrics_res.json()
