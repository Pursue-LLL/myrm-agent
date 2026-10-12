"""Integration tests for Semantic Layer RBAC API endpoints."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.security.semantic_rbac_router import router as semantic_rbac_router


@pytest.fixture(scope="function")
def client() -> TestClient:
    """Fixture providing test client mounting semantic_rbac_router."""
    test_app = FastAPI(title="Semantic RBAC Test App")
    test_app.include_router(semantic_rbac_router, prefix="/api/v1/security")
    return TestClient(test_app, raise_server_exceptions=False)


def test_get_view_and_register_view_endpoints(client: TestClient) -> None:
    # 1. Get default view
    resp = client.get("/api/v1/security/semantic-rbac/views/enterprise_sales")
    assert resp.status_code == 200
    data = resp.json()
    assert data["view_name"] == "enterprise_sales"
    assert any(c["name"] == "base_cost" for c in data["columns"])

    # 2. Register custom view
    reg_payload = {
        "view_name": "procurement_items",
        "columns": [
            {"name": "item_id", "data_type": "string", "access_modifier": "PUBLIC"},
            {"name": "tenant_id", "data_type": "string", "access_modifier": "PUBLIC"},
            {"name": "dept_id", "data_type": "string", "access_modifier": "PUBLIC"},
            {"name": "unit_cost", "data_type": "float", "access_modifier": "PRIVATE_ACCESS"},
        ],
        "tenant_column": "tenant_id",
        "dept_column": "dept_id",
    }
    reg_resp = client.post("/api/v1/security/semantic-rbac/views", json=reg_payload)
    assert reg_resp.status_code == 201
    assert reg_resp.json()["view_name"] == "procurement_items"


def test_plan_query_security_checks(client: TestClient) -> None:
    # 1. Unauthorized private fact projection rejected with 403
    forbidden_payload = {
        "view_name": "enterprise_sales",
        "requested_columns": ["order_id", "base_cost"],
        "aggregated_metrics": [],
        "identity": {
            "user_id": "u1",
            "tenant_id": "t1",
            "dept_id": "d1",
            "role": "sales",
            "is_admin": False,
        },
    }
    resp1 = client.post("/api/v1/security/semantic-rbac/plan", json=forbidden_payload)
    assert resp1.status_code == 403
    assert "marked as private_access" in resp1.json()["detail"]

    # 2. Restricted column projection by unauthorized role rejected with 400
    restricted_payload = {
        "view_name": "enterprise_sales",
        "requested_columns": ["order_id", "executive_margin"],
        "aggregated_metrics": [],
        "identity": {
            "user_id": "u1",
            "tenant_id": "t1",
            "dept_id": "d1",
            "role": "sales",
            "is_admin": False,
        },
    }
    resp2 = client.post("/api/v1/security/semantic-rbac/plan", json=restricted_payload)
    assert resp2.status_code == 400
    assert "not authorized to project column" in resp2.json()["detail"]

    # 3. CFO permitted to project executive_margin
    cfo_payload = {
        "view_name": "enterprise_sales",
        "requested_columns": ["order_id", "executive_margin"],
        "aggregated_metrics": [],
        "identity": {
            "user_id": "u2",
            "tenant_id": "t1",
            "dept_id": "d1",
            "role": "cfo",
            "is_admin": False,
        },
    }
    resp3 = client.post("/api/v1/security/semantic-rbac/plan", json=cfo_payload)
    assert resp3.status_code == 200
    assert "executive_margin" in resp3.json()["projected_columns"]


def test_execute_query_endpoint(client: TestClient) -> None:
    exec_payload = {
        "view_name": "enterprise_sales",
        "requested_columns": [],
        "aggregated_metrics": ["SUM(base_cost)"],
        "identity": {
            "user_id": "user-east",
            "tenant_id": "corp",
            "dept_id": "east",
            "role": "analyst",
            "is_admin": False,
        },
        "raw_data": [
            {"order_id": "1", "tenant_id": "corp", "dept_id": "east", "base_cost": 30.0},
            {"order_id": "2", "tenant_id": "corp", "dept_id": "east", "base_cost": 70.0},
            {"order_id": "3", "tenant_id": "corp", "dept_id": "west", "base_cost": 100.0},
        ],
    }

    resp = client.post("/api/v1/security/semantic-rbac/execute", json=exec_payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_rows"] == 1
    # Only items 1 & 2 in corp + east: 30 + 70 = 100
    assert data["rows"][0]["SUM(base_cost)"] == 100.0
