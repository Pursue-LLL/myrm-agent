"""Live-server E2E: trusted_desktop_apps persists through Agent CRUD API."""

from __future__ import annotations

import os

import httpx
import pytest

BASE_URL = os.getenv("TEST_BASE_URL", "http://localhost:8080")
_E2E_TIMEOUT = httpx.Timeout(10.0)


def _e2e_request(method: str, url: str, **kwargs: object) -> httpx.Response:
    with httpx.Client(trust_env=False, timeout=_E2E_TIMEOUT) as client:
        return client.request(method, url, **kwargs)


_skip_e2e = pytest.mark.skipif(
    not os.getenv("RUN_E2E_TESTS"),
    reason="Set RUN_E2E_TESTS=1 to run end-to-end tests against live server",
)


@pytest.fixture(scope="module")
def auth_headers() -> dict[str, str]:
    try:
        resp = _e2e_request(
            "POST",
            f"{BASE_URL}/api/v1/auth/login",
            json={
                "username": os.getenv("TEST_USERNAME", "test"),
                "password": os.getenv("TEST_PASSWORD", "test"),
            },
        )
    except (httpx.TimeoutException, httpx.ConnectError):
        return {}

    if resp.status_code == 200:
        token = resp.json().get("data", {}).get("access_token")
        if token:
            return {"Authorization": f"Bearer {token}"}
    return {}


@pytest.fixture
def created_agent_id(auth_headers: dict[str, str]):
    resp = _e2e_request(
        "POST",
        f"{BASE_URL}/api/v1/user-agents",
        json={
            "name": "Trusted Desktop Apps E2E Agent",
            "system_prompt": "You are a test agent.",
            "trusted_desktop_apps": [{"name": "SAP GUI", "app_id": "com.sap.gui"}],
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    agent_id = resp.json()["data"]["id"]
    yield agent_id
    _e2e_request(
        "DELETE",
        f"{BASE_URL}/api/v1/user-agents/{agent_id}",
        headers=auth_headers,
    )


@_skip_e2e
class TestTrustedDesktopAppsLiveCRUD:
    def test_create_read_update_round_trip(
        self,
        auth_headers: dict[str, str],
        created_agent_id: str,
    ) -> None:
        get_resp = _e2e_request(
            "GET",
            f"{BASE_URL}/api/v1/user-agents/{created_agent_id}",
            headers=auth_headers,
        )
        assert get_resp.status_code == 200, get_resp.text
        assert get_resp.json()["data"]["trusted_desktop_apps"] == [
            {"name": "SAP GUI", "app_id": "com.sap.gui"}
        ]

        update_resp = _e2e_request(
            "PUT",
            f"{BASE_URL}/api/v1/user-agents/{created_agent_id}",
            json={"trusted_desktop_apps": [{"name": "Legacy ERP"}]},
            headers=auth_headers,
        )
        assert update_resp.status_code == 200, update_resp.text
        assert update_resp.json()["data"]["trusted_desktop_apps"] == [
            {"name": "Legacy ERP"}
        ]
