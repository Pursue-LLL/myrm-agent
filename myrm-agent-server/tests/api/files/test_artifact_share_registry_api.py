"""Artifact share-link lifecycle through the management API: create registers, list, revoke, public access after revoke."""

from __future__ import annotations

import time
import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.services.artifacts.share.share_registry import token_fingerprint
from app.services.artifacts.share.share_token import create_artifact_share_token
from app.services.hosting.packager import PublishFile

pytestmark = pytest.mark.usefixtures("chats_share_workspace")


def _single_file_files():
    return {
        "index.html": PublishFile(path="index.html", content="<html></html>", encoding="utf-8"),
    }


# ---------------------------------------------------------------------------
# API: create registers, list, revoke, public access after revoke
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_registers_record(share_client, html_artifact) -> None:
    with patch(
        "app.services.artifacts.share.share_bundle.resolve_artifact_deploy_files",
        new_callable=AsyncMock,
        return_value=(html_artifact, _single_file_files()),
    ):
        response = share_client.post(
            f"/{html_artifact.id}/share-preview",
            json={"ttl_days": 7, "artifact_type": "html"},
        )
    assert response.status_code == 200
    token = response.json()["token"]
    assert token_fingerprint(token) is not None


@pytest.mark.asyncio
async def test_list_shares_endpoint(share_client, html_artifact) -> None:
    with patch(
        "app.services.artifacts.share.share_bundle.resolve_artifact_deploy_files",
        new_callable=AsyncMock,
        return_value=(html_artifact, _single_file_files()),
    ):
        create_resp = share_client.post(
            f"/{html_artifact.id}/share-preview",
            json={"ttl_days": 7, "artifact_type": "html"},
        )
    assert create_resp.status_code == 200
    original_token = create_resp.json()["token"]

    list_resp = share_client.get("/shares")
    assert list_resp.status_code == 200
    payload = list_resp.json()
    assert len(payload) == 1
    row = payload[0]
    assert row["artifact_name"] == "index.html"
    assert row["artifact_type"] == "html"
    assert row["password_protected"] is False
    assert row["expires_at"] > int(time.time())
    # Unprotected shares expose a rebuilt share_path that points at the token.
    assert row["share_path"] == f"/api/v1/public/artifact-share/{original_token}"
    # No public ingress configured in tests, so no absolute share_url.
    assert row["share_url"] is None


@pytest.mark.asyncio
async def test_list_shares_endpoint_exposes_absolute_share_url(share_client, html_artifact) -> None:
    """List exposes an absolute share_url once public ingress is configured."""
    with patch(
        "app.services.artifacts.share.share_bundle.resolve_artifact_deploy_files",
        new_callable=AsyncMock,
        return_value=(html_artifact, _single_file_files()),
    ):
        create_resp = share_client.post(
            f"/{html_artifact.id}/share-preview",
            json={"ttl_days": 7, "artifact_type": "html"},
        )
    assert create_resp.status_code == 200
    token = create_resp.json()["token"]

    with patch(
        "app.core.infra.ingress.get_public_ingress_base_url",
        new_callable=AsyncMock,
        return_value="https://myrm-x.example.com",
    ):
        list_resp = share_client.get("/shares")
    assert list_resp.status_code == 200
    row = list_resp.json()[0]
    assert row["share_url"] == (f"https://myrm-x.example.com/api/v1/public/artifact-share/{token}")


@pytest.mark.asyncio
async def test_list_shares_password_protected_exposes_persisted_share_path(share_client, html_artifact) -> None:
    """Password-protected shares persist share_path at register time.

    The token cannot be rebuilt because the password is never stored, so the
    management GUI needs the path stored on the row to offer copy/open links.
    """
    with patch(
        "app.services.artifacts.share.share_bundle.resolve_artifact_deploy_files",
        new_callable=AsyncMock,
        return_value=(html_artifact, _single_file_files()),
    ):
        create_resp = share_client.post(
            f"/{html_artifact.id}/share-preview",
            json={"ttl_days": 7, "artifact_type": "html", "password": "s3cret"},
        )
    assert create_resp.status_code == 200
    created_path = create_resp.json()["share_path"]

    list_resp = share_client.get("/shares")
    assert list_resp.status_code == 200
    row = list_resp.json()[0]
    assert row["password_protected"] is True
    assert row["share_path"] == created_path
    assert row["share_path"].startswith("/api/v1/public/artifact-share/")


@pytest.mark.asyncio
async def test_revoke_share_endpoint_and_public_denied(share_client, html_artifact, tmp_path) -> None:
    with patch(
        "app.services.artifacts.share.share_bundle.resolve_artifact_deploy_files",
        new_callable=AsyncMock,
        return_value=(html_artifact, _single_file_files()),
    ):
        create_resp = share_client.post(
            f"/{html_artifact.id}/share-preview",
            json={"ttl_days": 7, "artifact_type": "html"},
        )
    assert create_resp.status_code == 200

    list_resp = share_client.get("/shares")
    record_id = list_resp.json()[0]["id"]

    delete_resp = share_client.delete(f"/shares/{record_id}")
    assert delete_resp.status_code == 204

    # Repeating the delete is idempotent (204).
    repeat_resp = share_client.delete(f"/shares/{record_id}")
    assert repeat_resp.status_code == 204

    list_after = share_client.get("/shares")
    assert list_after.json() == []


@pytest.mark.asyncio
async def test_revoke_unknown_record_returns_404(share_client) -> None:
    response = share_client.delete(f"/shares/{uuid.uuid4()}")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"]


@pytest.mark.asyncio
async def test_register_share_failure_returns_500(share_client, html_artifact) -> None:
    with (
        patch(
            "app.services.artifacts.share.share_bundle.resolve_artifact_deploy_files",
            new_callable=AsyncMock,
            return_value=(html_artifact, _single_file_files()),
        ),
        patch(
            "app.services.artifacts.share.share_create.register_share",
            new_callable=AsyncMock,
            side_effect=RuntimeError("db down"),
        ),
    ):
        response = share_client.post(
            f"/{html_artifact.id}/share-preview",
            json={"ttl_days": 7, "artifact_type": "html"},
        )
    assert response.status_code == 500
    assert "register" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_public_access_denied_after_revoke(share_client, html_artifact, tmp_path) -> None:
    """A revoked token returns 404 even though its bundle was materialized."""
    with patch(
        "app.services.artifacts.share.share_bundle.resolve_artifact_deploy_files",
        new_callable=AsyncMock,
        return_value=(html_artifact, _single_file_files()),
    ):
        create_resp = share_client.post(
            f"/{html_artifact.id}/share-preview",
            json={"ttl_days": 7, "artifact_type": "html"},
        )
    assert create_resp.status_code == 200
    token = create_resp.json()["token"]

    # Ensure the public URL is servable before revoke.
    serve_before = share_client.get(f"/public/artifact-share/{token}", follow_redirects=False)
    assert serve_before.status_code == 200

    record_id = share_client.get("/shares").json()[0]["id"]
    assert share_client.delete(f"/shares/{record_id}").status_code == 204

    # Registry gate rejects regardless of on-disk bundle state.
    serve_after = share_client.get(f"/public/artifact-share/{token}", follow_redirects=False)
    assert serve_after.status_code == 404
    assert "revoked" in serve_after.json()["detail"]


@pytest.mark.asyncio
async def test_public_access_denied_for_a_token_that_was_never_registered(share_client, html_artifact) -> None:
    """A signed token nobody registered cannot be listed or revoked, so the public entry refuses it."""
    token, _ = create_artifact_share_token(html_artifact.id, "ver-1", ttl_seconds=3600)

    response = share_client.get(f"/public/artifact-share/{token}", follow_redirects=False)

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_revoked_share_browser_gets_status_page(share_client, html_artifact, tmp_path) -> None:
    """A revoked token answers browsers with a friendly status page, API JSON 404."""
    with patch(
        "app.services.artifacts.share.share_bundle.resolve_artifact_deploy_files",
        new_callable=AsyncMock,
        return_value=(html_artifact, _single_file_files()),
    ):
        create_resp = share_client.post(
            f"/{html_artifact.id}/share-preview",
            json={"ttl_days": 7, "artifact_type": "html"},
        )
    assert create_resp.status_code == 200
    token = create_resp.json()["token"]

    record_id = share_client.get("/shares").json()[0]["id"]
    assert share_client.delete(f"/shares/{record_id}").status_code == 204

    html_resp = share_client.get(
        f"/public/artifact-share/{token}",
        headers={"Accept": "text/html"},
        follow_redirects=False,
    )
    json_resp = share_client.get(
        f"/public/artifact-share/{token}",
        headers={"Accept": "application/json"},
        follow_redirects=False,
    )
    assert html_resp.status_code == 404
    assert html_resp.headers["content-type"].startswith("text/html")
    assert html_resp.headers["x-robots-tag"] == "noindex, nofollow"
    assert html_resp.headers["cache-control"] == "no-store"
    assert "Link Revoked" in html_resp.text
    assert json_resp.status_code == 404
    assert json_resp.headers["content-type"].startswith("application/json")
    assert "revoked" in json_resp.json()["detail"]


@pytest.mark.asyncio
async def test_revoked_password_share_skips_password_gate(share_client, html_artifact) -> None:
    """A revoked password-protected token 404s immediately, without a gate page."""
    with patch(
        "app.services.artifacts.share.share_bundle.resolve_artifact_deploy_files",
        new_callable=AsyncMock,
        return_value=(html_artifact, _single_file_files()),
    ):
        create_resp = share_client.post(
            f"/{html_artifact.id}/share-preview",
            json={"ttl_days": 7, "artifact_type": "html", "password": "s3cret"},
        )
    assert create_resp.status_code == 200
    token = create_resp.json()["token"]

    record_id = share_client.get("/shares").json()[0]["id"]
    assert share_client.delete(f"/shares/{record_id}").status_code == 204

    denied = share_client.get(f"/public/artifact-share/{token}", follow_redirects=False)
    assert denied.status_code == 404
    assert "revoked" in denied.json()["detail"]
