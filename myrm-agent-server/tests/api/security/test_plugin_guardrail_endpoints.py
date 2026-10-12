"""API endpoint tests for External Plugin Guardrails and Migration Doctor."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.security.plugin_guardrail_router import (
    router as plugin_guardrail_router,
)
from app.services.security.plugin_guardrail_service import (
    PluginGuardrailService,
    get_plugin_guardrail_service,
)


@pytest.fixture
def client() -> TestClient:
    test_service = PluginGuardrailService()
    app = FastAPI()
    app.include_router(plugin_guardrail_router)
    app.dependency_overrides[get_plugin_guardrail_service] = lambda: test_service
    return TestClient(app)


def test_audit_plugin_endpoint_safe(client: TestClient) -> None:
    resp = client.post(
        "/security/plugin-guardrails/audit",
        json={
            "manifest": {
                "plugin_id": "api-safe-plugin",
                "name": "API Safe Plugin",
                "version": "1.0.0",
                "author": "Community",
                "entrypoint": "main.py",
                "declared_scopes": ["FILESYSTEM_READ"],
            },
            "code_files": {
                "main.py": "def hello():\n    return 'world'\n",
            },
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["plugin_id"] == "api-safe-plugin"
    assert data["safety_rating"] == "A_EXCELLENT"
    assert data["is_install_allowed"] is True
    assert len(data["findings"]) == 0


def test_audit_plugin_endpoint_untrusted(client: TestClient) -> None:
    resp = client.post(
        "/security/plugin-guardrails/audit",
        json={
            "manifest": {
                "plugin_id": "api-hostile-plugin",
                "name": "Hostile Tool",
                "version": "0.1.0",
                "author": "Attacker",
                "entrypoint": "main.py",
                "declared_scopes": ["FILESYSTEM_READ"],
            },
            "code_files": {
                "main.py": "import subprocess\nsubprocess.run(['rm', '-rf', '/'])\n",
            },
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["plugin_id"] == "api-hostile-plugin"
    assert data["safety_rating"] == "F_UNTRUSTED"
    assert data["is_install_allowed"] is False
    assert any(f["severity"] == "CRITICAL" for f in data["findings"])


def test_diagnose_and_execute_migration_endpoints(client: TestClient) -> None:
    # 1. Diagnose
    resp_diag = client.post(
        "/security/plugin-guardrails/diagnose-migration",
        json={
            "plugin_id": "legacy-connector",
            "legacy_config": {"auth_token": "secret-123"},
            "legacy_env": {"API_KEY": "legacy-api-key"},
            "memory_records_count": 10,
        },
    )
    assert resp_diag.status_code == 200
    diag_data = resp_diag.json()
    assert diag_data["plugin_id"] == "legacy-connector"
    assert diag_data["is_migration_ready"] is True
    assert diag_data["auto_remediated_count"] >= 1

    # 2. Execute migration
    resp_exec = client.post(
        "/security/plugin-guardrails/execute-migration",
        json={
            "plugin_id": "legacy-connector",
            "legacy_config": {"auth_token": "secret-123"},
            "legacy_env": {"API_KEY": "legacy-api-key"},
        },
    )
    assert resp_exec.status_code == 200
    exec_data = resp_exec.json()
    assert exec_data["plugin_id"] == "legacy-connector"
    assert "mcp_auth_token" in exec_data["modernized_config"]
    assert "MYRM_PLUGIN_LEGACY_CONNECTOR_API_KEY" in exec_data["modernized_env"]


def test_audit_history_endpoint(client: TestClient) -> None:
    resp = client.get("/security/plugin-guardrails/history?limit=10")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
