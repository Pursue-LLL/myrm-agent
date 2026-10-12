"""API endpoint tests for SSO Redirect Idempotence and Probe Hysteresis.

Verifies HTTP endpoints for building idempotent SSO redirect URLs, validating
safe navigation targets against open redirects, and network probe hysteresis.
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.security.sso_redirect_idempotent_router import (
    get_sso_redirect_idempotent_service,
)
from app.api.security.sso_redirect_idempotent_router import (
    router as sso_redirect_idempotent_router,
)
from app.services.security.sso_redirect_idempotent_service import (
    SsoRedirectIdempotentService,
)


def create_test_client() -> TestClient:
    app = FastAPI()
    service = SsoRedirectIdempotentService()
    app.dependency_overrides[get_sso_redirect_idempotent_service] = lambda: service
    app.include_router(
        sso_redirect_idempotent_router, prefix="/api/v1/security"
    )
    return TestClient(app)


def test_build_redirect_url_endpoint() -> None:
    client = create_test_client()

    payload = {
        "redirect_uri": "/portal/dashboard?filter=recent&sso_code=old-code",
        "sso_code": "new-code-999",
        "param_name": "sso_code",
    }
    resp = client.post(
        "/api/v1/security/sso-redirect-idempotent/build-redirect-url",
        json=payload,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert (
        data["redirect_url"]
        == "/portal/dashboard?filter=recent&sso_code=new-code-999"
    )
    assert data["stripped_existing_code"] is True
    assert data["is_relative"] is True
    assert data["is_safe_target"] is True


def test_validate_navigation_target_endpoint() -> None:
    client = create_test_client()

    # Valid relative path
    resp_valid = client.post(
        "/api/v1/security/sso-redirect-idempotent/validate-navigation-target",
        json={"target": "/settings/profile"},
    )
    assert resp_valid.status_code == 200
    assert resp_valid.json()["is_safe"] is True
    assert resp_valid.json()["is_same_origin_relative"] is True
    assert resp_valid.json()["resolved_safe_target"] == "/settings/profile"

    # WHATWG open redirect exploit attempt
    resp_exploit = client.post(
        "/api/v1/security/sso-redirect-idempotent/validate-navigation-target",
        json={"target": "/\\malicious-site.com", "fallback_url": "/dashboard"},
    )
    assert resp_exploit.status_code == 200
    assert resp_exploit.json()["is_safe"] is False
    assert resp_exploit.json()["is_same_origin_relative"] is False
    assert resp_exploit.json()["resolved_safe_target"] == "/dashboard"


def test_record_probe_endpoint() -> None:
    client = create_test_client()

    # Initial healthy probe
    resp1 = client.post(
        "/api/v1/security/sso-redirect-idempotent/record-probe",
        json={"healthy": True, "current_url": "/session/view/100"},
    )
    assert resp1.status_code == 200
    assert resp1.json()["is_online"] is True
    assert resp1.json()["suggested_navigation_url"] == "/session/view/100"

    # Transient failures (1 and 2): dampened!
    client.post(
        "/api/v1/security/sso-redirect-idempotent/record-probe",
        json={"healthy": False},
    )
    resp_fail2 = client.post(
        "/api/v1/security/sso-redirect-idempotent/record-probe",
        json={"healthy": False},
    )
    assert resp_fail2.status_code == 200
    assert resp_fail2.json()["is_online"] is True
    assert resp_fail2.json()["transitioned_to_offline"] is False
    assert resp_fail2.json()["consecutive_fails"] == 2

    # Third failure: switches to offline
    resp_fail3 = client.post(
        "/api/v1/security/sso-redirect-idempotent/record-probe",
        json={"healthy": False},
    )
    assert resp_fail3.status_code == 200
    assert resp_fail3.json()["is_online"] is False
    assert resp_fail3.json()["transitioned_to_offline"] is True
    assert resp_fail3.json()["suggested_navigation_url"] == "/offline"

    # Single recovery probe brings it back online
    resp_recover = client.post(
        "/api/v1/security/sso-redirect-idempotent/record-probe",
        json={"healthy": True},
    )
    assert resp_recover.status_code == 200
    assert resp_recover.json()["is_online"] is True
    assert resp_recover.json()["transitioned_to_online"] is True
    assert resp_recover.json()["suggested_navigation_url"] == "/session/view/100"
