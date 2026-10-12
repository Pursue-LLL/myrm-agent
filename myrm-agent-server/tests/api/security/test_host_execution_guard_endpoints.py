"""
[POS] tests/api/security/test_host_execution_guard_endpoints.py
[INPUT] fastapi, fastapi.testclient, tmp_path, app.api.security.host_execution_guard_router, app.services.security.host_execution_guard_service
[OUTPUT] Endpoint integration tests

Validates FastAPI REST endpoints for Local Host Safe Execution Sandbox & Non-Destructive Guardrail.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from myrm_agent_harness.core.security.host_execution_guard import HostExecutionGuardSuite

from app.api.security.host_execution_guard_router import router as host_guard_router
from app.services.security.host_execution_guard_service import (
    HostExecutionGuardService,
    get_host_execution_guard_service,
)


@pytest.fixture
def test_setup(tmp_path: Path) -> tuple[TestClient, Path]:
    ws = tmp_path / "workspace"
    ws.mkdir()
    scratch = tmp_path / "scratch"
    scratch.mkdir()

    suite = HostExecutionGuardSuite(
        workspace_root=str(ws),
        scratch_overlay_dir=str(scratch),
    )
    service = HostExecutionGuardService(suite=suite)

    app = FastAPI()
    app.include_router(host_guard_router)
    app.dependency_overrides[get_host_execution_guard_service] = lambda: service

    return TestClient(app), ws


def test_path_inspection_endpoints(test_setup: tuple[TestClient, Path]) -> None:
    """Validate POST /host-execution-guard/paths/inspect."""
    client, ws = test_setup

    # 1. Inspect system write with overlay redirect
    res_overlay = client.post(
        "/host-execution-guard/paths/inspect",
        json={"target_path": "/usr/lib/libc.so", "mode": "WRITE"},
    )
    assert res_overlay.status_code == 200
    odata = res_overlay.json()
    assert odata["is_protected"] is True
    assert odata["action"] == "VIRTUAL_OVERLAY"

    # 2. Inspect credential read
    res_cred = client.post(
        "/host-execution-guard/paths/inspect",
        json={"target_path": "~/.ssh/id_ed25519", "mode": "READ"},
    )
    assert res_cred.status_code == 200
    cdata = res_cred.json()
    assert cdata["action"] == "BLOCK"

    # 3. Inspect workspace file write
    res_ws = client.post(
        "/host-execution-guard/paths/inspect",
        json={"target_path": str(ws / "main.py"), "mode": "WRITE"},
    )
    assert res_ws.status_code == 200
    wdata = res_ws.json()
    assert wdata["action"] == "ALLOW"


def test_command_inspection_and_hitl_endpoints(test_setup: tuple[TestClient, Path]) -> None:
    """Validate command inspection, pending queue, approval, and rejection endpoints."""
    client, _ = test_setup

    # 1. Catastrophic command
    res_cat = client.post(
        "/host-execution-guard/commands/inspect",
        json={"command": "rm -rf /"},
    )
    assert res_cat.status_code == 200
    assert res_cat.json()["risk_level"] == "BLOCKED_DESTRUCTIVE"
    assert res_cat.json()["is_blocked"] is True

    # 2. High-risk command requiring HITL
    res_hitl = client.post(
        "/host-execution-guard/commands/inspect",
        json={"command": "rm -rf ./cache_dir"},
    )
    assert res_hitl.status_code == 200
    hdata = res_hitl.json()
    assert hdata["risk_level"] == "REQUIRE_HITL"
    assert hdata["requires_hitl"] is True
    insp_id = hdata["inspection_id"]

    # 3. List pending commands
    res_pending = client.get("/host-execution-guard/commands/pending")
    assert res_pending.status_code == 200
    pdata = res_pending.json()
    assert len(pdata) == 1
    assert pdata[0]["inspection_id"] == insp_id

    # 4. Approve command
    res_appr = client.post(
        "/host-execution-guard/commands/approve",
        json={"inspection_id": insp_id},
    )
    assert res_appr.status_code == 200
    assert res_appr.json()["risk_level"] == "SAFE"

    # 5. Reject command
    res_hitl2 = client.post(
        "/host-execution-guard/commands/inspect",
        json={"command": "reboot"},
    )
    insp2_id = res_hitl2.json()["inspection_id"]
    res_rej = client.post(
        "/host-execution-guard/commands/reject",
        json={"inspection_id": insp2_id},
    )
    assert res_rej.status_code == 200
    assert res_rej.json()["risk_level"] == "BLOCKED_DESTRUCTIVE"


def test_workspace_snapshot_and_rollback_endpoints(test_setup: tuple[TestClient, Path]) -> None:
    """Validate snapshot creation, retrieval, and atomic rollback endpoints."""
    client, ws = test_setup

    f1 = ws / "app.py"
    f1.write_text("VERSION = '1.0.0'\n", encoding="utf-8")
    f2_rel = "temp_scratch.py"

    # 1. Create snapshot
    res_snap = client.post(
        "/host-execution-guard/snapshots",
        json={
            "workspace_root": str(ws),
            "target_rel_paths": ["app.py", f2_rel],
            "description": "Pre-edit snapshot",
        },
    )
    assert res_snap.status_code == 201
    sdata = res_snap.json()
    snap_id = sdata["snapshot_id"]
    assert sdata["is_restored"] is False

    # 2. Corrupt app.py and create temp_scratch.py
    f1.write_text("CORRUPTED_CODE\n", encoding="utf-8")
    f2 = ws / f2_rel
    f2.write_text("scratch\n", encoding="utf-8")

    # 3. Retrieve snapshot list and single snapshot
    res_list = client.get("/host-execution-guard/snapshots")
    assert res_list.status_code == 200
    assert any(s["snapshot_id"] == snap_id for s in res_list.json())

    res_single = client.get(f"/host-execution-guard/snapshots/{snap_id}")
    assert res_single.status_code == 200
    assert res_single.json()["snapshot_id"] == snap_id

    # 4. Rollback snapshot
    res_rb = client.post(
        "/host-execution-guard/snapshots/rollback",
        json={"snapshot_id": snap_id},
    )
    assert res_rb.status_code == 200
    assert res_rb.json()["is_restored"] is True
    assert f1.read_text(encoding="utf-8") == "VERSION = '1.0.0'\n"
    assert not f2.exists()

    # 5. Check metrics
    res_m = client.get("/host-execution-guard/metrics")
    assert res_m.status_code == 200
    mdata = res_m.json()
    assert mdata["snapshots_created_total"] == 1
    assert mdata["rollbacks_executed_total"] == 1
