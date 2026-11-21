"""Hosting targets and credentials API — real routes and database; external HTTP only mocked."""

from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest

from app.services.hosting.targets import save_hosting_targets
from app.services.hosting.types import HostingTarget
from tests.support.hosting_api import public_dns, seed_webhook_target


@pytest.mark.asyncio
async def test_target_credentials_are_write_only(hosting_integration_client) -> None:
    client, _workspace, db_session = hosting_integration_client
    target_id = f"cred-int-{uuid.uuid4().hex[:8]}"
    await save_hosting_targets(
        db_session,
        [HostingTarget(id=target_id, name="Vercel", provider_type="vercel", config={}, is_default=True)],
    )

    put = client.put(
        f"/hosting/targets/{target_id}/credentials",
        json={"credentials": {"token": "vc_secret"}},
    )
    assert put.status_code == 200

    get = client.get(f"/hosting/targets/{target_id}/credentials")
    assert get.status_code == 200
    assert get.json() == {"configured": True, "platform_available": False}
    assert "vc_secret" not in get.text


@pytest.mark.asyncio
async def test_test_connection_webhook_validates_url(hosting_integration_client) -> None:
    client, _workspace, db_session = hosting_integration_client
    target_id = f"wh-test-{uuid.uuid4().hex[:8]}"
    await seed_webhook_target(db_session, target_id)

    with patch("app.services.hosting.ssrf_guard.socket.getaddrinfo", side_effect=public_dns):
        response = client.post(f"/hosting/targets/{target_id}/test")

    assert response.status_code == 200
    assert response.json()["ok"] is True


@pytest.mark.asyncio
async def test_target_crud_lifecycle_matches_frontend(hosting_integration_client) -> None:
    client, _workspace, db_session = hosting_integration_client
    create = client.post(
        "/hosting/targets",
        json={
            "name": "Lifecycle Webhook",
            "provider_type": "http_webhook",
            "config": {"webhook_url": "https://hooks.example.com/lifecycle", "allow_http": "false"},
            "is_default": True,
        },
    )
    assert create.status_code == 200
    target_id = create.json()["id"]

    update = client.put(
        f"/hosting/targets/{target_id}",
        json={
            "name": "Lifecycle Updated",
            "provider_type": "http_webhook",
            "config": {"webhook_url": "https://hooks.example.com/lifecycle-v2", "allow_http": "false"},
            "is_default": True,
        },
    )
    assert update.status_code == 200
    assert update.json()["name"] == "Lifecycle Updated"

    with patch("app.services.hosting.ssrf_guard.socket.getaddrinfo", side_effect=public_dns):
        test_resp = client.post(f"/hosting/targets/{target_id}/test")
    assert test_resp.status_code == 200
    assert test_resp.json()["ok"] is True

    delete = client.delete(f"/hosting/targets/{target_id}")
    assert delete.status_code == 200
    assert client.get("/hosting/targets").json()["targets"] == []


@pytest.mark.asyncio
async def test_update_and_delete_target_not_found(hosting_integration_client) -> None:
    client, _, _db = hosting_integration_client
    missing = "missing-target-id"
    update = client.put(
        f"/hosting/targets/{missing}",
        json={"name": "X", "provider_type": "vercel", "config": {}, "is_default": False},
    )
    assert update.status_code == 404
    delete = client.delete(f"/hosting/targets/{missing}")
    assert delete.status_code == 404


@pytest.mark.asyncio
async def test_webhook_credentials_status_without_secrets(hosting_integration_client) -> None:
    client, _workspace, db_session = hosting_integration_client
    target_id = f"wh-cred-{uuid.uuid4().hex[:8]}"
    await seed_webhook_target(db_session, target_id)
    response = client.get(f"/hosting/targets/{target_id}/credentials")
    assert response.status_code == 200
    assert response.json() == {"configured": True, "platform_available": False}


@pytest.mark.asyncio
async def test_make_default_missing_target_404(hosting_integration_client) -> None:
    client, _, _db = hosting_integration_client
    response = client.post("/hosting/targets/does-not-exist/make-default")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_put_credentials_missing_target_404(hosting_integration_client) -> None:
    client, _, _db = hosting_integration_client
    response = client.put(
        "/hosting/targets/missing-target/credentials",
        json={"credentials": {"token": "x"}},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_test_connection_vercel_without_credentials(hosting_integration_client) -> None:
    client, _workspace, db_session = hosting_integration_client
    target_id = f"vercel-test-{uuid.uuid4().hex[:8]}"
    await save_hosting_targets(
        db_session,
        [
            HostingTarget(
                id=target_id,
                name="Vercel",
                provider_type="vercel",
                config={},
                is_default=True,
            )
        ],
    )
    with patch("app.services.hosting.credentials.get_platform_vercel_token", return_value=None):
        response = client.post(f"/hosting/targets/{target_id}/test")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert "credentials" in body["message"].lower() or "token" in body["message"].lower()
