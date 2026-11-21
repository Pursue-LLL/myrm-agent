"""Password-protected shares: the gate, unlock cookies and unlock credentials."""

from __future__ import annotations

import time
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import Response

from app.api.files.artifact_share_public import (
    _attach_unlock_cookie,
    _unlock_claims_from_cookie,
)
from app.core.security.share.share_hmac import create_share_token
from app.core.security.share.share_unlock import build_unlock_credential, unlock_cookie_name
from app.database.models.artifact import Artifact, ArtifactVersion
from app.services.artifacts.share.share_token import (
    ArtifactShareClaims,
)
from app.services.hosting.packager import PublishFile

pytestmark = pytest.mark.usefixtures("chats_share_workspace")


@pytest.mark.asyncio
async def test_password_share_unlock_cookie_keeps_extensionless_media_type(share_client, db_session, workspace) -> None:
    """Unlock-cookie auth keeps artifact_type for extension-less PDF entries.

    A password share of a PDF whose artifact name has no suffix (entry file has
    no extension) must still be served as ``application/pdf`` when the browser
    refreshes and authenticates via the unlock cookie instead of ``p``.
    """
    from myrm_agent_harness.agent.artifacts.vault import ArtifactVault

    vault = ArtifactVault(str(workspace))
    uri = vault.put("%PDF-1.4 dummy", "report")

    artifact = Artifact(
        id=str(uuid.uuid4()),
        name="report",
        chat_id=str(uuid.uuid4()),
        is_deleted=False,
    )
    db_session.add(artifact)
    await db_session.commit()
    ver = ArtifactVersion(
        id=str(uuid.uuid4()),
        artifact_id=artifact.id,
        vault_uri=uri,
        sha256_hash="h_pdf_noext",
    )
    db_session.add(ver)
    await db_session.commit()
    await db_session.refresh(artifact)

    with patch(
        "app.services.hosting.artifact_files.ensure_artifact_for_deploy",
        new_callable=AsyncMock,
        return_value=artifact,
    ):
        resp = share_client.post(
            f"/{artifact.id}/share-preview",
            json={"ttl_days": 7, "artifact_type": "pdf", "password": "s3cret"},
        )
    assert resp.status_code == 200
    token = resp.json()["token"]

    first = share_client.get(f"/public/artifact-share/{token}?p=s3cret", follow_redirects=False)
    assert first.status_code == 200
    assert first.headers["content-type"].startswith("application/pdf")
    cookie_name = unlock_cookie_name("artifact_share_unlock", token)
    unlock = share_client.cookies.get(cookie_name)
    assert unlock is not None

    # Test router mounts under /public/artifact-share while the cookie path is
    # the production /api/v1/... prefix, so TestClient's jar would not auto-send
    # it; pass the cookie explicitly like the other unlock-cookie tests.
    refreshed = share_client.get(
        f"/public/artifact-share/{token}/",
        headers={"Cookie": f"{cookie_name}={unlock}"},
        follow_redirects=False,
    )
    assert refreshed.status_code == 200
    assert refreshed.headers["content-type"].startswith("application/pdf")


@pytest.mark.asyncio
async def test_password_share_redirect_preserves_query(share_client, html_artifact) -> None:
    """307 redirect for multi-file password shares must keep the ``p`` query."""
    files = {
        "index.html": PublishFile(
            path="index.html",
            content='<html><link href="styles.css"/></html>',
            encoding="utf-8",
        ),
        "styles.css": PublishFile(path="styles.css", content="body{}", encoding="utf-8"),
    }
    with patch(
        "app.services.artifacts.share.share_bundle.resolve_artifact_deploy_files",
        new_callable=AsyncMock,
        return_value=(html_artifact, files),
    ):
        response = share_client.post(
            f"/{html_artifact.id}/share-preview",
            json={"ttl_days": 7, "artifact_type": "html", "password": "s3cret"},
        )
    token = response.json()["token"]
    redirect = share_client.get(
        f"/public/artifact-share/{token}?p=s3cret",
        follow_redirects=False,
    )
    assert redirect.status_code == 307
    assert redirect.headers["location"].endswith(f"/{token}/?p=s3cret")
    assert share_client.cookies.get(unlock_cookie_name("artifact_share_unlock", token)) is not None


@pytest.mark.asyncio
async def test_password_share_asset_requires_credential(share_client, html_artifact) -> None:
    """Static assets of a password-protected share are gated without credentials."""
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
            json={"ttl_days": 7, "artifact_type": "html", "password": "s3cret"},
        )
    token = response.json()["token"]
    blocked = share_client.get(f"/public/artifact-share/{token}/styles.css")
    assert blocked.status_code == 403
    assert "Password Required" in blocked.text


@pytest.mark.asyncio
async def test_password_share_asset_served_after_unlock(share_client, html_artifact) -> None:
    """Once unlocked via ``p``, the unlock cookie authorizes static assets."""
    files = {
        "index.html": PublishFile(
            path="index.html",
            content='<html><link href="styles.css"/></html>',
            encoding="utf-8",
        ),
        "styles.css": PublishFile(path="styles.css", content="body{}", encoding="utf-8"),
    }
    with patch(
        "app.services.artifacts.share.share_bundle.resolve_artifact_deploy_files",
        new_callable=AsyncMock,
        return_value=(html_artifact, files),
    ):
        response = share_client.post(
            f"/{html_artifact.id}/share-preview",
            json={"ttl_days": 7, "artifact_type": "html", "password": "s3cret"},
        )
    token = response.json()["token"]
    entry = share_client.get(f"/public/artifact-share/{token}/?p=s3cret", follow_redirects=False)
    assert entry.status_code == 200
    cookie_name = unlock_cookie_name("artifact_share_unlock", token)
    unlock = share_client.cookies.get(cookie_name)
    assert unlock is not None

    asset = share_client.get(
        f"/public/artifact-share/{token}/styles.css",
        headers={"Cookie": f"{cookie_name}={unlock}"},
    )
    assert asset.status_code == 200
    assert "body" in asset.text


@pytest.mark.asyncio
async def test_password_single_file_share_serves_without_redirect(share_client, html_artifact) -> None:
    """Single-file password shares keep serving inline with a Set-Cookie unlock."""
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
            json={"ttl_days": 7, "artifact_type": "html", "password": "s3cret"},
        )
    token = response.json()["token"]
    entry = share_client.get(f"/public/artifact-share/{token}?p=s3cret", follow_redirects=False)
    assert entry.status_code == 200
    assert "set-cookie" in entry.headers
    assert share_client.cookies.get(unlock_cookie_name("artifact_share_unlock", token)) is not None


@pytest.mark.asyncio
async def test_password_share_wrong_password_gate(share_client, html_artifact) -> None:
    """A wrong password renders the password gate again, never a 404."""
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
            json={"ttl_days": 7, "artifact_type": "html", "password": "s3cret"},
        )
    token = response.json()["token"]
    gate = share_client.get(f"/public/artifact-share/{token}?p=wrong", follow_redirects=False)
    assert gate.status_code == 403
    assert "Incorrect password" in gate.text


@pytest.mark.asyncio
async def test_password_shares_use_independent_cookies(share_client, html_artifact, db_session) -> None:
    """Concurrent password-protected shares must not collide on a shared cookie.

    Each share gets a token-bound cookie name, so unlocking one share never
    authorizes asset requests against another share's bundle.
    """
    second_artifact = Artifact(
        id=str(uuid.uuid4()),
        name="report.html",
        chat_id=str(uuid.uuid4()),
        is_deleted=False,
    )
    db_session.add(second_artifact)
    await db_session.commit()
    second_version = ArtifactVersion(
        id=str(uuid.uuid4()),
        artifact_id=second_artifact.id,
        vault_uri="vault://report",
        sha256_hash="hash",
    )
    db_session.add(second_version)
    await db_session.commit()
    await db_session.refresh(second_artifact)

    files = {
        "index.html": PublishFile(
            path="index.html",
            content='<html><link href="styles.css"/></html>',
            encoding="utf-8",
        ),
        "styles.css": PublishFile(path="styles.css", content="body{}", encoding="utf-8"),
    }
    with patch(
        "app.services.artifacts.share.share_bundle.resolve_artifact_deploy_files",
        new_callable=AsyncMock,
        return_value=(html_artifact, files),
    ):
        first = share_client.post(
            f"/{html_artifact.id}/share-preview",
            json={"ttl_days": 7, "artifact_type": "html", "password": "s3cret"},
        )
    with patch(
        "app.services.artifacts.share.share_bundle.resolve_artifact_deploy_files",
        new_callable=AsyncMock,
        return_value=(second_artifact, files),
    ):
        second = share_client.post(
            f"/{second_artifact.id}/share-preview",
            json={"ttl_days": 7, "artifact_type": "html", "password": "s3cret"},
        )
    first_token = first.json()["token"]
    second_token = second.json()["token"]
    assert unlock_cookie_name("artifact_share_unlock", first_token) != unlock_cookie_name("artifact_share_unlock", second_token)

    first_entry = share_client.get(f"/public/artifact-share/{first_token}/?p=s3cret", follow_redirects=False)
    assert first_entry.status_code == 200
    first_unlock = share_client.cookies.get(unlock_cookie_name("artifact_share_unlock", first_token))
    assert first_unlock is not None

    second_entry = share_client.get(f"/public/artifact-share/{second_token}/?p=s3cret", follow_redirects=False)
    assert second_entry.status_code == 200

    first_asset = share_client.get(
        f"/public/artifact-share/{first_token}/styles.css",
        headers={"Cookie": f"{unlock_cookie_name('artifact_share_unlock', first_token)}={first_unlock}"},
    )
    assert first_asset.status_code == 200
    assert "body" in first_asset.text


def test_unlock_credential_rejects_short_remaining() -> None:
    """No unlock cookie is issued when the share is about to expire."""
    claims = ArtifactShareClaims(artifact_id="a", version_id="v", exp=int(time.time()) + 30)
    assert build_unlock_credential({"aid": "a", "vid": "v"}, salt="artifact-share-unlock", exp=claims.exp) is None


def test_unlock_credential_roundtrip() -> None:
    """A valid credential round-trips through claims recovery."""
    claims = ArtifactShareClaims(artifact_id="a", version_id="v", exp=int(time.time()) + 3600)
    credential = build_unlock_credential({"aid": "a", "vid": "v"}, salt="artifact-share-unlock", exp=claims.exp)
    assert credential is not None
    recovered = _unlock_claims_from_cookie(credential)
    assert recovered is not None
    assert recovered.artifact_id == "a"
    assert recovered.version_id == "v"


def test_unlock_credential_roundtrip_keeps_artifact_type() -> None:
    """The unlock cookie must not drop artifact_type for extension-less entries."""
    claims = ArtifactShareClaims(
        artifact_id="a",
        version_id="v",
        exp=int(time.time()) + 3600,
        artifact_type="document",
    )
    credential = build_unlock_credential(
        {"aid": "a", "vid": "v", "typ": "document"},
        salt="artifact-share-unlock",
        exp=claims.exp,
    )
    assert credential is not None
    recovered = _unlock_claims_from_cookie(credential)
    assert recovered is not None
    assert recovered.artifact_type == "document"


def test_unlock_claims_rejects_garbage() -> None:
    """Malformed or forged unlock cookies are rejected, not crashed on."""
    assert _unlock_claims_from_cookie("not-a-valid-credential") is None


def test_unlock_claims_rejects_missing_fields() -> None:
    """A valid signature without the artifact identity fields yields None."""
    credential, _ = create_share_token(
        {"foo": "bar"},
        salt="artifact-share-unlock",
        ttl_seconds=3600,
        max_ttl_seconds=30 * 24 * 3600,
    )
    assert _unlock_claims_from_cookie(credential) is None


def test_attach_unlock_cookie_skips_when_credential_unavailable() -> None:
    """No Set-Cookie when the share is too close to expiry to unlock."""
    response = Response()
    claims = ArtifactShareClaims(artifact_id="a", version_id="v", exp=int(time.time()) + 30)
    _attach_unlock_cookie(response, claims, "token", "pw", secure=False)
    assert "set-cookie" not in response.headers


@pytest.mark.asyncio
async def test_password_share_index_gate_without_password(share_client, html_artifact) -> None:
    """A password-protected multi-file share's index is gated without ``p``."""
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
            json={"ttl_days": 7, "artifact_type": "html", "password": "s3cret"},
        )
    token = response.json()["token"]
    gate = share_client.get(f"/public/artifact-share/{token}/", follow_redirects=False)
    assert gate.status_code == 403
    assert "password" in gate.text.lower()
