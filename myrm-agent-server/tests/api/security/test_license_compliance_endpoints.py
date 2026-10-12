"""Integration tests for License Compliance and Copyleft Gating API endpoints."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.security.license_compliance_router import (
    router as license_compliance_router,
)


@pytest.fixture(scope="function")
def client() -> TestClient:
    """Fixture providing test client mounting license_compliance_router."""
    test_app = FastAPI(title="License Compliance Test App")
    test_app.include_router(license_compliance_router, prefix="/api/v1/security")
    return TestClient(test_app, raise_server_exceptions=False)


def test_evaluate_asset_license_endpoint(client: TestClient) -> None:
    # 1. Evaluate permissive MIT license
    payload_mit = {
        "asset_id": "skill-markdown",
        "asset_type": "skill",
        "declared_license": "MIT",
        "environment": "CLOUD_COMMERCIAL",
        "allow_override": False,
    }
    resp = client.post("/api/v1/security/license-compliance/evaluate", json=payload_mit)
    assert resp.status_code == 200
    data = resp.json()
    assert data["decision"] == "ALLOWED"
    assert data["detected_license"]["risk_tier"] == "PERMISSIVE"

    # 2. Evaluate AGPL license without override -> BLOCKED in cloud
    payload_agpl = {
        "asset_id": "skill-pi-mem",
        "asset_type": "skill",
        "declared_license": "AGPL-3.0",
        "environment": "CLOUD_COMMERCIAL",
        "allow_override": False,
    }
    resp_agpl = client.post("/api/v1/security/license-compliance/evaluate", json=payload_agpl)
    assert resp_agpl.status_code == 200
    data_agpl = resp_agpl.json()
    assert data_agpl["decision"] == "BLOCKED_COPYLEFT_RESTRICTION"
    assert data_agpl["can_override"] is True

    # 3. Evaluate AGPL license with override -> WARNING_PROCEED
    payload_agpl["allow_override"] = True
    resp_override = client.post("/api/v1/security/license-compliance/evaluate", json=payload_agpl)
    assert resp_override.status_code == 200
    data_override = resp_override.json()
    assert data_override["decision"] == "WARNING_PROCEED"


def test_asset_lifecycle_and_inventory_endpoints(client: TestClient) -> None:
    # 1. Register asset
    create_payload = {
        "asset_id": "mcp-pgvector",
        "asset_type": "mcp_server",
        "declared_license": "Apache-2.0",
        "package_url": "pkg:generic/mcp-pgvector@1.0.0",
    }
    create_resp = client.post("/api/v1/security/license-compliance/assets", json=create_payload)
    assert create_resp.status_code == 201
    created_data = create_resp.json()
    assert created_data["asset_id"] == "mcp-pgvector"
    assert created_data["detected_license"]["spdx_id"] == "Apache-2.0"

    # 2. List assets
    list_resp = client.get("/api/v1/security/license-compliance/assets")
    assert list_resp.status_code == 200
    assets = list_resp.json()
    assert any(a["asset_id"] == "mcp-pgvector" for a in assets)

    # 3. Get inventory summary
    summary_resp = client.get("/api/v1/security/license-compliance/summary?environment=CLOUD_COMMERCIAL")
    assert summary_resp.status_code == 200
    summary = summary_resp.json()
    assert summary["total_assets"] >= 1
    assert summary["permissive_count"] >= 1

    # 4. Export CycloneDX records
    export_resp = client.get("/api/v1/security/license-compliance/export/cyclonedx")
    assert export_resp.status_code == 200
    records = export_resp.json()
    assert any(r["bom_ref"] == "mcp-pgvector" for r in records)

    # 5. Delete asset
    del_resp = client.delete("/api/v1/security/license-compliance/assets/mcp-pgvector")
    assert del_resp.status_code == 200
    assert del_resp.json()["success"] is True

    # 6. Delete again -> 404
    del_404 = client.delete("/api/v1/security/license-compliance/assets/mcp-pgvector")
    assert del_404.status_code == 404
