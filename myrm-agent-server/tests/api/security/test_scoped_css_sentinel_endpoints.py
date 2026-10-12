"""API endpoint tests for Scoped CSS Isolation and Parallel Micro-Agent Boundary Sentinel."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.security.scoped_css_sentinel_router import (
    router as scoped_css_sentinel_router,
)
from app.services.security.scoped_css_sentinel_service import (
    ScopedCssSentinelService,
    get_scoped_css_sentinel_service,
)


@pytest.fixture
def client() -> TestClient:
    test_service = ScopedCssSentinelService()
    app = FastAPI()
    app.include_router(scoped_css_sentinel_router, prefix="/api/v1/security")
    app.dependency_overrides[get_scoped_css_sentinel_service] = lambda: test_service
    return TestClient(app)


def test_scope_endpoint_valid_and_violation(client: TestClient) -> None:
    # 1. Valid CSS scoping
    resp_valid = client.post(
        "/api/v1/security/scoped-css-sentinel/scope",
        json={
            "css_content": ".btn { color: white; } .panel { margin: 10px; }",
            "scope_id": "drawer-dialog",
        },
    )
    assert resp_valid.status_code == 200
    valid_data = resp_valid.json()
    assert valid_data["is_valid"] is True
    assert valid_data["scope_id"] == "#drawer-dialog"
    assert valid_data["rules_rewritten"] == 2
    assert "#drawer-dialog .btn" in valid_data["scoped_css"]

    # 2. Violation: global root selector 'body'
    resp_invalid = client.post(
        "/api/v1/security/scoped-css-sentinel/scope",
        json={
            "css_content": "body { background: #000; }",
            "scope_id": "#modal",
        },
    )
    assert resp_invalid.status_code == 200
    invalid_data = resp_invalid.json()
    assert invalid_data["is_valid"] is False
    assert len(invalid_data["violations"]) >= 1
    assert "body" in invalid_data["violations"][0]["selector"]


def test_conflicts_endpoint_orthogonal_and_collision(client: TestClient) -> None:
    # 1. Orthogonal non-colliding patches
    resp_orth = client.post(
        "/api/v1/security/scoped-css-sentinel/conflicts",
        json={
            "patches": [
                {
                    "agent_id": "agent_alpha",
                    "component_target_id": "drawer-panel",
                    "css_content": ".title { font-weight: bold; }",
                },
                {
                    "agent_id": "agent_beta",
                    "component_target_id": "footer-bar",
                    "css_content": ".copy { font-size: 12px; }",
                },
            ]
        },
    )
    assert resp_orth.status_code == 200
    orth_data = resp_orth.json()
    assert orth_data["has_conflict"] is False
    assert orth_data["conflicting_agents"] == []
    assert "#drawer-panel .title" in orth_data["merged_scoped_css"]
    assert "#footer-bar .copy" in orth_data["merged_scoped_css"]

    # 2. Collision: multiple agents targeting same component
    resp_coll = client.post(
        "/api/v1/security/scoped-css-sentinel/conflicts",
        json={
            "patches": [
                {
                    "agent_id": "agent_1",
                    "component_target_id": "shared-header",
                    "css_content": ".logo { width: 100px; }",
                },
                {
                    "agent_id": "agent_2",
                    "component_target_id": "shared-header",
                    "css_content": ".logo { width: 120px; }",
                },
            ]
        },
    )
    assert resp_coll.status_code == 200
    coll_data = resp_coll.json()
    assert coll_data["has_conflict"] is True
    assert set(coll_data["conflicting_agents"]) == {"agent_1", "agent_2"}
    assert coll_data["merged_scoped_css"] is None
