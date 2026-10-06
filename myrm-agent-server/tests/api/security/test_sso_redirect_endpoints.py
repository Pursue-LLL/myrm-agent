"""Integration tests for SSO Redirect API endpoints.

[INPUT]
- HTTP requests to /api/v1/security/sso-redirect/* endpoints.

[OUTPUT]
- Verified JSON responses for redirect URL validation, idempotent URL generation,
  and connection probe hysteresis evaluation.

[POS]
- Server integration test suite for IHUI-AI #2728e745 idempotent redirect and probe hysteresis.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.security.sso_redirect_router import (
    get_sso_redirect_service,
)
from app.api.security.sso_redirect_router import (
    router as sso_redirect_router,
)
from app.schemas.sso_redirect import UrlPathCategoryDto
from app.services.security.sso_redirect_service import SsoRedirectService


@pytest.fixture(scope="function")
def isolated_service() -> SsoRedirectService:
    """Fixture providing isolated service instance."""
    return SsoRedirectService()


@pytest.fixture(scope="function")
def client(isolated_service: SsoRedirectService) -> TestClient:
    """Fixture providing test client mounting sso_redirect_router."""
    test_app = FastAPI(title="SSO Redirect Test App")
    test_app.dependency_overrides[get_sso_redirect_service] = (
        lambda: isolated_service
    )
    test_app.include_router(
        sso_redirect_router, prefix="/api/v1/security"
    )
    return TestClient(test_app, raise_server_exceptions=False)


def test_validate_redirect_target_endpoints(client: TestClient) -> None:
    # 1. Safe relative target
    resp_rel = client.post(
        "/api/v1/security/sso-redirect/validate-target",
        json={"target_url": "/dashboard/reports?view=summary"},
    )
    assert resp_rel.status_code == 200
    data_rel = resp_rel.json()
    assert data_rel["is_safe"] is True
    assert data_rel["category"] == UrlPathCategoryDto.SAFE_RELATIVE.value

    # 2. Open redirect scheme-relative attack
    resp_attack = client.post(
        "/api/v1/security/sso-redirect/validate-target",
        json={"target_url": "//evil.org/phish"},
    )
    assert resp_attack.status_code == 200
    data_attack = resp_attack.json()
    assert data_attack["is_safe"] is False
    assert data_attack["category"] == UrlPathCategoryDto.UNSAFE_RELATIVE.value

    # 3. Whitelisted absolute host
    resp_whitelisted = client.post(
        "/api/v1/security/sso-redirect/validate-target",
        json={
            "target_url": "https://auth.acme.com/login",
            "allowed_absolute_hosts": ["auth.acme.com"],
        },
    )
    assert resp_whitelisted.status_code == 200
    assert resp_whitelisted.json()["is_safe"] is True


def test_build_sso_redirect_url_endpoint(client: TestClient) -> None:
    # Build URL with existing sso_code to verify idempotence
    resp = client.post(
        "/api/v1/security/sso-redirect/build-url",
        json={
            "redirect_uri": "/sso/callback?tab=main&sso_code=OLD_CODE",
            "sso_code": "FRESH_CODE_123",
            "code_param": "sso_code",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["final_url"] == "/sso/callback?tab=main&sso_code=FRESH_CODE_123"
    assert "OLD_CODE" not in data["final_url"]
    assert data["is_relative"] is True


def test_evaluate_probe_endpoint(client: TestClient) -> None:
    # 1. First failure -> degraded
    r1 = client.post("/api/v1/security/sso-redirect/evaluate-probe", json={"is_success": False})
    assert r1.status_code == 200
    d1 = r1.json()
    assert d1["new_state"] == "degraded"
    assert d1["consecutive_failures"] == 1

    # 2. Second failure -> still degraded
    r2 = client.post("/api/v1/security/sso-redirect/evaluate-probe", json={"is_success": False})
    assert r2.status_code == 200
    assert r2.json()["new_state"] == "degraded"

    # 3. Third failure -> offline
    r3 = client.post("/api/v1/security/sso-redirect/evaluate-probe", json={"is_success": False})
    assert r3.status_code == 200
    assert r3.json()["new_state"] == "offline"
    assert r3.json()["recommended_action"] == "switch_to_offline_fallback"

    # 4. Immediate recovery on success
    r4 = client.post("/api/v1/security/sso-redirect/evaluate-probe", json={"is_success": True})
    assert r4.status_code == 200
    assert r4.json()["new_state"] == "online"
    assert r4.json()["consecutive_failures"] == 0
