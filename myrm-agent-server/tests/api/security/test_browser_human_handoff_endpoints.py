"""
Integration tests for Browser Human Handoff Gate Suite REST API endpoints.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.security.browser_human_handoff_router import (
    router as browser_human_handoff_router,
)
from app.services.security.browser_human_handoff_service import (
    BrowserHumanHandoffService,
    get_browser_human_handoff_service,
)


@pytest.fixture
def client() -> TestClient:
    service = BrowserHumanHandoffService()
    app = FastAPI()
    app.include_router(browser_human_handoff_router)
    app.dependency_overrides[get_browser_human_handoff_service] = lambda: service
    return TestClient(app)


def test_inspect_page_safety_captcha_and_resolve(client: TestClient) -> None:
    # 1. Post page with captcha
    response = client.post(
        "/browser-human-handoff/inspect-page-safety",
        json={
            "html_or_dom": "<html><body><iframe src='https://challenges.cloudflare.com/cdn-cgi/challenge-platform/h/b/turnstile/if/ov2/av0/rcv/0/abc'></iframe></body></html>",
            "url": "https://auth.example.com",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["interception"]["is_handoff_required"] is True
    assert data["interception"]["trigger_type"] == "CAPTCHA_CHALLENGE"
    interception_id = data["interception"]["interception_id"]

    # 2. Query pending handoffs
    pending_resp = client.get("/browser-human-handoff/pending-handoffs")
    assert pending_resp.status_code == 200
    pending_list = pending_resp.json()
    assert len(pending_list) == 1
    assert pending_list[0]["interception_id"] == interception_id

    # 3. Resolve handoff
    resolve_resp = client.post(
        "/browser-human-handoff/resolve-handoff",
        json={"interception_id": interception_id},
    )
    assert resolve_resp.status_code == 200
    assert resolve_resp.json()["is_resolved"] is True

    # 4. Resolve non-existent handoff returns 404
    missing_resp = client.post(
        "/browser-human-handoff/resolve-handoff",
        json={"interception_id": "non-existent-id"},
    )
    assert missing_resp.status_code == 404


def test_inspect_page_safety_zero_content(client: TestClient) -> None:
    response = client.post(
        "/browser-human-handoff/inspect-page-safety",
        json={
            "html_or_dom": "<html><body>   \n\t  </body></html>",
            "url": "https://whiteout.example.com",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["interception"]["is_handoff_required"] is True
    assert data["interception"]["trigger_type"] == "ZERO_CONTENT_CORRUPTION"
    assert data["health"]["is_corrupted_zero_content"] is True


def test_browser_profile_lease_endpoints(client: TestClient) -> None:
    # 1. Acquire lease
    acquire_resp = client.post(
        "/browser-human-handoff/acquire-lease",
        json={
            "profile_name": "developer-default",
            "consumer_id": "agent-cursor-01",
            "ttl_seconds": 60.0,
        },
    )
    assert acquire_resp.status_code == 201
    lease = acquire_resp.json()
    lease_id = lease["lease_id"]
    assert lease["status"] == "LEASED"

    # 2. Concurrent collision returns 409 Conflict
    conflict_resp = client.post(
        "/browser-human-handoff/acquire-lease",
        json={
            "profile_name": "developer-default",
            "consumer_id": "agent-claude-02",
            "ttl_seconds": 60.0,
        },
    )
    assert conflict_resp.status_code == 409

    # 3. Query active lease by name
    get_resp = client.get("/browser-human-handoff/active-lease/developer-default")
    assert get_resp.status_code == 200
    assert get_resp.json()["lease_id"] == lease_id

    # 4. List all active leases
    list_resp = client.get("/browser-human-handoff/active-leases")
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1

    # 5. Release lease
    release_resp = client.post(
        "/browser-human-handoff/release-lease",
        json={"lease_id": lease_id},
    )
    assert release_resp.status_code == 200
    assert release_resp.json()["status"] == "RELEASED"

    # 6. Release missing lease returns 404
    missing_release = client.post(
        "/browser-human-handoff/release-lease",
        json={"lease_id": "non-existent-lease"},
    )
    assert missing_release.status_code == 404

    # 7. Check metrics
    metrics_resp = client.get("/browser-human-handoff/metrics")
    assert metrics_resp.status_code == 200
    metrics = metrics_resp.json()
    assert metrics["browser_leases_granted_total"] == 1
    assert metrics["browser_leases_released_total"] == 1
