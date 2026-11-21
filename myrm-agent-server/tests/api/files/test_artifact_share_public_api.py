"""Serving a created share through the public routes: tokens, bundles, nested assets and serve-time errors."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.api.files.artifact_share_public import (
    _serve_share_bundle,
)
from app.services.artifacts.share.share_token import (
    ArtifactShareClaims,
    parse_artifact_share_token,
)
from app.services.hosting.packager import PublishFile

pytestmark = pytest.mark.usefixtures("chats_share_workspace")


def _api_client_request() -> Request:
    """A browser-free request scope so status helpers raise JSON 404s."""
    return Request(
        scope={
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [(b"accept", b"application/json")],
            "server": ("testserver", 80),
            "client": ("testclient", 50000),
            "scheme": "http",
            "query_string": b"",
            "root_path": "",
        }
    )


@pytest.mark.asyncio
async def test_public_share_invalid_token(share_client) -> None:
    response = share_client.get("/public/artifact-share/not-a-valid-token")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_single_file_share_serves_without_redirect(share_client, html_artifact) -> None:
    files = {
        "report.pdf": PublishFile(path="report.pdf", content="JVBERi0=", encoding="base64"),
    }
    with patch(
        "app.services.artifacts.share.share_bundle.resolve_artifact_deploy_files",
        new_callable=AsyncMock,
        return_value=(html_artifact, files),
    ):
        response = share_client.post(
            f"/{html_artifact.id}/share-preview",
            json={"ttl_days": 7, "artifact_type": "pdf"},
        )
    assert response.status_code == 200
    token = response.json()["token"]
    entry = share_client.get(f"/public/artifact-share/{token}", follow_redirects=False)
    assert entry.status_code == 200


@pytest.mark.asyncio
async def test_public_share_expired_token(share_client, html_artifact) -> None:
    files = {
        "index.html": PublishFile(path="index.html", content="<html/>", encoding="utf-8"),
    }
    with patch(
        "app.services.artifacts.share.share_bundle.resolve_artifact_deploy_files",
        new_callable=AsyncMock,
        return_value=(html_artifact, files),
    ):
        response = share_client.post(
            f"/{html_artifact.id}/share-preview",
            json={"ttl_days": 7, "artifact_type": "html"},
        )
    token = response.json()["token"]
    claims = parse_artifact_share_token(token)
    assert claims is not None
    with patch(
        "app.core.security.share.share_hmac.time.time",
        return_value=claims.exp + 1,
    ):
        expired = share_client.get(f"/public/artifact-share/{token}")
    assert expired.status_code == 404


@pytest.mark.asyncio
async def test_public_share_nested_asset_path(share_client, html_artifact) -> None:
    files = {
        "index.html": PublishFile(
            path="index.html",
            content='<html><link rel="stylesheet" href="assets/styles.css"/></html>',
            encoding="utf-8",
        ),
        "assets/styles.css": PublishFile(
            path="assets/styles.css",
            content=".x{color:red}",
            encoding="utf-8",
        ),
    }
    with patch(
        "app.services.artifacts.share.share_bundle.resolve_artifact_deploy_files",
        new_callable=AsyncMock,
        return_value=(html_artifact, files),
    ):
        response = share_client.post(
            f"/{html_artifact.id}/share-preview",
            json={"ttl_days": 7, "artifact_type": "html"},
        )
    token = response.json()["token"]
    css = share_client.get(f"/public/artifact-share/{token}/assets/styles.css")
    assert css.status_code == 200
    assert "color:red" in css.text


@pytest.mark.asyncio
async def test_public_share_manifest_not_served(share_client, html_artifact) -> None:
    files = {
        "index.html": PublishFile(path="index.html", content="<html/>", encoding="utf-8"),
        "styles.css": PublishFile(path="styles.css", content="body{}", encoding="utf-8"),
    }
    with patch(
        "app.services.artifacts.share.share_bundle.resolve_artifact_deploy_files",
        new_callable=AsyncMock,
        return_value=(html_artifact, files),
    ):
        response = share_client.post(
            f"/{html_artifact.id}/share-preview",
            json={"ttl_days": 7, "artifact_type": "html"},
        )
    token = response.json()["token"]
    manifest = share_client.get(f"/public/artifact-share/{token}/manifest.json")
    assert manifest.status_code == 404


@pytest.mark.parametrize(
    ("exc", "status"),
    [
        (LookupError("gone"), 404),
        (FileNotFoundError("gone"), 404),
        (RuntimeError("boom"), 500),
    ],
)
@pytest.mark.asyncio
async def test_serve_bundle_materialize_error_mapping(share_client, exc: Exception, status: int) -> None:
    claims = ArtifactShareClaims(artifact_id="a", version_id="v", exp=int(time.time()) + 3600)
    with (
        patch(
            "app.api.files.artifact_share_public.resolve_share_bundle_file",
            return_value=None,
        ),
        patch(
            "app.api.files.artifact_share_public.materialize_share_bundle",
            new_callable=AsyncMock,
            side_effect=exc,
        ),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await _serve_share_bundle(claims, "token", None, "/tmp", None, _api_client_request())
    assert exc_info.value.status_code == status


@pytest.mark.asyncio
async def test_serve_bundle_missing_after_materialize(share_client) -> None:
    """A bundle that still resolves to nothing after materialize is a 404."""
    claims = ArtifactShareClaims(artifact_id="a", version_id="v", exp=int(time.time()) + 3600)
    with (
        patch(
            "app.api.files.artifact_share_public.resolve_share_bundle_file",
            return_value=None,
        ),
        patch(
            "app.api.files.artifact_share_public.materialize_share_bundle",
            new_callable=AsyncMock,
        ),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await _serve_share_bundle(claims, "token", None, "/tmp", None, _api_client_request())
    assert exc_info.value.status_code == 404
