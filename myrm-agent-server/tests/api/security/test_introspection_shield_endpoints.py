"""
[POS] tests/api/security/test_introspection_shield_endpoints.py
[INPUT] fastapi, fastapi.testclient, tmp_path, app.api.security.introspection_shield_router, app.services.security.introspection_shield_service
[OUTPUT] Endpoint integration tests

Validates FastAPI REST endpoints for Agent Runtime Introspection Shield & Decoupled Workspace Template Suite.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.security.introspection_shield_router import router as shield_router
from app.services.security.introspection_shield_service import (
    IntrospectionShieldService,
    get_introspection_shield_service,
)


@pytest.fixture
def client() -> TestClient:
    test_service = IntrospectionShieldService()
    app = FastAPI()
    app.include_router(shield_router)
    app.dependency_overrides[get_introspection_shield_service] = lambda: test_service
    return TestClient(app)


def test_evaluate_path_endpoints(client: TestClient, tmp_path: Path) -> None:
    """Validate POST /introspection-shield/evaluate-path endpoint."""
    # 1. Safe workspace target
    safe_res = client.post(
        "/introspection-shield/evaluate-path",
        json={
            "target_path": "README.md",
            "workspace_root": str(tmp_path),
        },
    )
    assert safe_res.status_code == 200
    s_data = safe_res.json()
    assert not s_data["is_blocked"]
    assert s_data["action_taken"] == "ALLOW_UNRESTRICTED"

    # 2. Blocked host path (/opt/hatch/config.yaml)
    blocked_res = client.post(
        "/introspection-shield/evaluate-path",
        json={
            "target_path": "/opt/hatch/config.yaml",
            "workspace_root": str(tmp_path),
        },
    )
    assert blocked_res.status_code == 200
    b_data = blocked_res.json()
    assert b_data["is_blocked"]
    assert b_data["probe_type"] == "HOST_PATH_PROBE"
    assert b_data["action_taken"] == "FAKE_ROOT_REDIRECT"


def test_scaffold_and_hydrate_endpoints(client: TestClient, tmp_path: Path) -> None:
    """Validate POST /scaffold-templates and POST /hydrate-templates."""
    # 1. Scaffold templates
    scaffold_res = client.post(
        "/introspection-shield/scaffold-templates",
        json={
            "workspace_dir": str(tmp_path),
            "overwrite": False,
        },
    )
    assert scaffold_res.status_code == 201
    sc_data = scaffold_res.json()
    assert len(sc_data["created_files"]) == 5
    assert "SOUL.md" in sc_data["created_files"]

    # 2. Hydrate templates
    hydrate_res = client.post(
        "/introspection-shield/hydrate-templates",
        json={
            "workspace_dir": str(tmp_path),
        },
    )
    assert hydrate_res.status_code == 200
    h_data = hydrate_res.json()
    assert len(h_data["templates"]) == 5
    assert "<workspace_standards>" in h_data["prompt_context"]
    assert h_data["total_characters"] > 0


def test_metrics_and_patterns_endpoints(client: TestClient) -> None:
    """Validate GET /metrics and GET /blackhole-patterns."""
    # 1. Patterns
    patterns_res = client.get("/introspection-shield/blackhole-patterns")
    assert patterns_res.status_code == 200
    p_data = patterns_res.json()
    assert p_data["count"] > 10
    assert "/opt/**" in p_data["patterns"]

    # 2. Metrics
    metrics_res = client.get("/introspection-shield/metrics")
    assert metrics_res.status_code == 200
    m_data = metrics_res.json()
    assert m_data["probes_evaluated"] >= 0
