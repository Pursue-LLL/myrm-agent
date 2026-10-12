"""Integration tests for Four-Zone Workspace Layout API endpoints."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from myrm_agent_harness.core.security.four_zone import WorkspaceZone

from app.api.workspace.four_zone_router import router as four_zone_router


@pytest.fixture(scope="function")
def client() -> TestClient:
    """Fixture providing test client mounting four_zone_router."""
    test_app = FastAPI(title="Four-Zone Workspace Test App")
    test_app.include_router(four_zone_router, prefix="/api/v1/workspace")
    return TestClient(test_app, raise_server_exceptions=False)


def test_four_zone_api_full_cycle(client: TestClient, tmp_path: Path) -> None:
    ws_root = str(tmp_path / "api_workspace")

    # 1. POST /scaffold
    scaffold_resp = client.post(
        "/api/v1/workspace/four-zone/scaffold",
        json={"workspace_root": ws_root},
    )
    assert scaffold_resp.status_code == 200
    scaffold_data = scaffold_resp.json()
    assert scaffold_data["status"] == "success"
    assert len(scaffold_data["zones"]) == 4

    # Put a client raw file into Zone 01
    raw_dir = Path(ws_root) / WorkspaceZone.ZONE_01_RAW.value
    raw_file = raw_dir / "invoice.pdf"
    raw_file.write_text("Original Invoice Bytes", encoding="utf-8")

    # 2. POST /check (READ on Zone 01 -> allowed)
    chk_read = client.post(
        "/api/v1/workspace/four-zone/check",
        json={"file_path": str(raw_file), "operation": "read"},
    )
    assert chk_read.status_code == 200
    assert chk_read.json()["allowed"] is True

    # 3. POST /check (WRITE on Zone 01 -> blocked)
    chk_write = client.post(
        "/api/v1/workspace/four-zone/check",
        json={"file_path": str(raw_file), "operation": "write"},
    )
    assert chk_write.status_code == 200
    write_data = chk_write.json()
    assert write_data["allowed"] is False
    assert "strictly READ-ONLY" in write_data["reason"]

    # 4. POST /replicate (Zone 01 -> Zone 02 draft)
    rep_resp = client.post(
        "/api/v1/workspace/four-zone/replicate",
        json={
            "workspace_root": ws_root,
            "source_rel_path": "invoice.pdf",
            "draft_rel_path": "invoice_draft.txt",
        },
    )
    assert rep_resp.status_code == 200
    rep_data = rep_resp.json()
    assert os.path.isfile(rep_data["draft_full_path"])

    # 5. POST /promote (Zone 02 -> Zone 03 canonical)
    prom_c_resp = client.post(
        "/api/v1/workspace/four-zone/promote",
        json={
            "workspace_root": ws_root,
            "source_rel_path": "invoice_draft.txt",
            "target_rel_path": "canonical_invoice.txt",
            "promotion_type": "draft_to_canonical",
            "reviewer_id": "auditor_1",
        },
    )
    assert prom_c_resp.status_code == 200
    prom_c_data = prom_c_resp.json()
    assert prom_c_data["source_zone"] == WorkspaceZone.ZONE_02_DRAFT.value
    assert prom_c_data["target_zone"] == WorkspaceZone.ZONE_03_CANONICAL.value

    # 6. POST /promote (Zone 03 -> Zone 04 deliverable)
    prom_d_resp = client.post(
        "/api/v1/workspace/four-zone/promote",
        json={
            "workspace_root": ws_root,
            "source_rel_path": "canonical_invoice.txt",
            "target_rel_path": "deliverable_invoice.txt",
            "promotion_type": "canonical_to_deliverable",
            "reviewer_id": "manager_2",
        },
    )
    assert prom_d_resp.status_code == 200
    prom_d_data = prom_d_resp.json()
    assert prom_d_data["source_zone"] == WorkspaceZone.ZONE_03_CANONICAL.value
    assert prom_d_data["target_zone"] == WorkspaceZone.ZONE_04_DELIVERABLE.value
