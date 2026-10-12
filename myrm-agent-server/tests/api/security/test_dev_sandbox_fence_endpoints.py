"""API endpoint tests for Zero-Production-Write Dev Sandbox and Synthetic Data Fence."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.security.dev_sandbox_fence_router import (
    router as dev_sandbox_fence_router,
)
from app.services.security.dev_sandbox_fence_service import (
    DevSandboxFenceService,
    get_dev_sandbox_fence_service,
)


@pytest.fixture
def client() -> TestClient:
    test_service = DevSandboxFenceService()
    app = FastAPI()
    app.include_router(dev_sandbox_fence_router, prefix="/api/v1/security")
    app.dependency_overrides[get_dev_sandbox_fence_service] = lambda: test_service
    return TestClient(app)


def test_inspect_endpoint(client: TestClient) -> None:
    # 1. Mutating SQL blocked
    resp_sql_bad = client.post(
        "/api/v1/security/dev-fence/inspect",
        json={
            "operation_type": "sql",
            "target": "patients",
            "payload": "INSERT INTO patients (id) VALUES (100)",
            "session_id": "api-s1",
        },
    )
    assert resp_sql_bad.status_code == 200
    data_sql_bad = resp_sql_bad.json()
    assert data_sql_bad["allowed"] is False
    assert data_sql_bad["violation_type"] == "prod_db_write_blocked"

    # 2. Read-only SQL allowed
    resp_sql_good = client.post(
        "/api/v1/security/dev-fence/inspect",
        json={
            "operation_type": "sql",
            "target": "patients",
            "payload": "SELECT count(*) FROM patients",
            "session_id": "api-s2",
        },
    )
    assert resp_sql_good.status_code == 200
    assert resp_sql_good.json()["allowed"] is True

    # 3. Main branch push blocked
    resp_branch = client.post(
        "/api/v1/security/dev-fence/inspect",
        json={
            "operation_type": "git_branch",
            "target": "main",
            "session_id": "api-s3",
        },
    )
    assert resp_branch.status_code == 200
    assert resp_branch.json()["allowed"] is False
    assert resp_branch.json()["violation_type"] == "prod_branch_push_blocked"

    # 4. Dev branch allowed
    resp_branch_ok = client.post(
        "/api/v1/security/dev-fence/inspect",
        json={
            "operation_type": "git_branch",
            "target": "agent/dev-fhir-sync",
            "session_id": "api-s4",
        },
    )
    assert resp_branch_ok.status_code == 200
    assert resp_branch_ok.json()["allowed"] is True

    # 5. Production DB substituted
    resp_db = client.post(
        "/api/v1/security/dev-fence/inspect",
        json={
            "operation_type": "db_connect",
            "target": "postgresql://prod-ehr:5432/live",
            "session_id": "api-s5",
        },
    )
    assert resp_db.status_code == 200
    data_db = resp_db.json()
    assert data_db["allowed"] is True
    assert data_db["violation_type"] == "prod_credential_substitution"
    assert "mock://" in data_db["substituted_target"]

    # 6. Sensitive file path blocked
    resp_file_bad = client.post(
        "/api/v1/security/dev-fence/inspect",
        json={
            "operation_type": "file_write",
            "target": ".github/workflows/deploy.yml",
            "session_id": "api-s6",
        },
    )
    assert resp_file_bad.status_code == 200
    assert resp_file_bad.json()["allowed"] is False
    assert resp_file_bad.json()["violation_type"] == "sensitive_dir_write_blocked"


def test_fixtures_endpoints(client: TestClient) -> None:
    # 1. List pre-loaded fixtures
    resp_list = client.get("/api/v1/security/dev-fence/fixtures")
    assert resp_list.status_code == 200
    fixtures = resp_list.json()
    ids = [f["fixture_id"] for f in fixtures]
    assert "synthetic_sqlite_memory" in ids

    # 2. Register new fixture
    resp_create = client.post(
        "/api/v1/security/dev-fence/fixtures",
        json={
            "fixture_id": "custom_mock_db",
            "database_type": "mysql",
            "read_only_uri": "mock://dev-mysql:3306/readonly",
            "sample_count": 50,
            "description": "Mock MySQL fixture",
        },
    )
    assert resp_create.status_code == 201
    assert resp_create.json()["fixture_id"] == "custom_mock_db"

    # 3. Delete fixture
    resp_del = client.delete("/api/v1/security/dev-fence/fixtures/custom_mock_db")
    assert resp_del.status_code == 200
    assert resp_del.json()["success"] is True

    # 4. Delete non-existent fixture
    resp_del_nf = client.delete("/api/v1/security/dev-fence/fixtures/non_existent_fixture")
    assert resp_del_nf.status_code == 404


def test_violations_endpoint(client: TestClient) -> None:
    # Trigger a violation
    client.post(
        "/api/v1/security/dev-fence/inspect",
        json={
            "operation_type": "sql",
            "target": "billing",
            "payload": "DROP TABLE billing",
            "session_id": "sess-violation-test",
        },
    )

    resp_viol = client.get("/api/v1/security/dev-fence/violations?session_id=sess-violation-test")
    assert resp_viol.status_code == 200
    viols = resp_viol.json()
    assert len(viols) == 1
    assert viols[0]["violation_type"] == "prod_db_write_blocked"


def test_policy_and_mode_endpoints(client: TestClient) -> None:
    # Query policy
    resp_pol = client.get("/api/v1/security/dev-fence/policy")
    assert resp_pol.status_code == 200
    data_pol = resp_pol.json()
    assert "main" in data_pol["blocked_branches"]
    assert data_pol["mode"] == "dev_isolated"

    # Update mode
    resp_mode = client.post(
        "/api/v1/security/dev-fence/mode",
        json={"mode": "readonly_research"},
    )
    assert resp_mode.status_code == 200
    assert resp_mode.json()["mode"] == "readonly_research"

    # Bad mode returns 400
    resp_bad = client.post(
        "/api/v1/security/dev-fence/mode",
        json={"mode": "invalid_mode_xyz"},
    )
    assert resp_bad.status_code == 400
