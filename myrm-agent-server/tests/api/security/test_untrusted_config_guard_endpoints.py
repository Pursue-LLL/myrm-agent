"""API endpoint tests for Untrusted Project Config Isolation and Preflight Diagnostic Gate."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.security.untrusted_config_guard_router import (
    router as untrusted_config_guard_router,
)
from app.services.security.untrusted_config_guard_service import (
    UntrustedConfigGuardService,
    get_untrusted_config_guard_service,
)


@pytest.fixture
def client() -> TestClient:
    test_service = UntrustedConfigGuardService()
    app = FastAPI()
    app.include_router(untrusted_config_guard_router, prefix="/api/v1/security")
    app.dependency_overrides[get_untrusted_config_guard_service] = lambda: test_service
    return TestClient(app)


def test_resolve_endpoint_untrusted_vs_trusted(client: TestClient, tmp_path: Path) -> None:
    ws_dir = tmp_path / "cloned_repo"
    ws_dir.mkdir()
    cfg_dir = ws_dir / ".myrm"
    cfg_dir.mkdir()
    (cfg_dir / "config.json").write_text(
        json.dumps({
            "version": "1.0",
            "model_tier": "untrusted_payload_tier",
            "execution_timeout": 90.0,
        }),
        encoding="utf-8",
    )

    # 1. Untrusted resolution
    resp_untrusted = client.post(
        "/api/v1/security/config-guard/resolve",
        json={"workspace_path": str(ws_dir), "is_project_trusted": False},
    )
    assert resp_untrusted.status_code == 200
    data_untrusted = resp_untrusted.json()
    assert data_untrusted["applied_tier"] == "local_project_untrusted_rejected"
    assert data_untrusted["effective_config"]["model_tier"] == "standard"

    # 2. Explicitly trust workspace via API
    resp_trust = client.post(
        "/api/v1/security/config-guard/trust",
        json={"workspace_path": str(ws_dir), "trusted": True},
    )
    assert resp_trust.status_code == 200
    assert resp_trust.json()["is_trusted"] is True

    # 3. Check trust status query
    resp_status = client.get(
        f"/api/v1/security/config-guard/trust-status?workspace_path={ws_dir}"
    )
    assert resp_status.status_code == 200
    assert resp_status.json()["is_trusted"] is True

    # 4. Now resolution applies local project config
    resp_trusted = client.post(
        "/api/v1/security/config-guard/resolve",
        json={"workspace_path": str(ws_dir)},
    )
    assert resp_trusted.status_code == 200
    data_trusted = resp_trusted.json()
    assert data_trusted["applied_tier"] == "local_project_trusted"
    assert data_trusted["effective_config"]["model_tier"] == "untrusted_payload_tier"
    assert data_trusted["effective_config"]["execution_timeout"] == 90.0


def test_preflight_validate_endpoint(client: TestClient) -> None:
    # 1. Valid JSON payload
    resp_valid = client.post(
        "/api/v1/security/config-guard/preflight-validate",
        json={"raw_json": json.dumps({"version": "1.0", "model_tier": "fast"})},
    )
    assert resp_valid.status_code == 200
    data_valid = resp_valid.json()
    assert data_valid["is_valid"] is True
    assert data_valid["unknown_keys"] == []
    assert data_valid["effective_config"]["model_tier"] == "fast"

    # 2. Injected unknown keys rejected
    resp_bad = client.post(
        "/api/v1/security/config-guard/preflight-validate",
        json={
            "config_dict": {
                "version": "1.0",
                "injected_unknown_parameter": "bad_value",
            }
        },
    )
    assert resp_bad.status_code == 200
    data_bad = resp_bad.json()
    assert data_bad["is_valid"] is False
    assert "injected_unknown_parameter" in data_bad["unknown_keys"]

    # 3. require_all_enabled assertion
    resp_req = client.post(
        "/api/v1/security/config-guard/preflight-validate",
        json={
            "config_dict": {
                "version": "1.0",
                "anti_exfiltration_guard": False,
            },
            "require_all_enabled": True,
        },
    )
    assert resp_req.status_code == 200
    data_req = resp_req.json()
    assert data_req["is_valid"] is False
    assert data_req["all_mandatory_features_enabled"] is False
