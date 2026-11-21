"""CWE-598: the password gate posts via the form body (POST), never the URL."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, patch

import pytest

from app.core.security.share.share_hmac import sign_share_token
from app.core.security.share.share_unlock import unlock_cookie_name
from app.services.hosting.packager import PublishFile

pytestmark = pytest.mark.usefixtures("chats_share_workspace")


# ---------------------------------------------------------------------------
# CWE-598: the password gate posts via form body (POST), never the URL
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_password_share_post_unlock_single_file(share_client, html_artifact) -> None:
    """POST form unlock keeps the password out of the URL and PRG-redirects.

    A successful POST for a single-file share answers 303 See Other to the
    clean GET URL and sets the unlock cookie, so the address bar never carries
    ``?p=...`` and a refresh cannot re-submit the password.
    """
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

    gate = share_client.get(f"/public/artifact-share/{token}", follow_redirects=False)
    assert gate.status_code == 403
    assert "password" in gate.text.lower()

    unlocked = share_client.post(
        f"/public/artifact-share/{token}",
        data={"p": "s3cret"},
        follow_redirects=False,
    )
    assert unlocked.status_code == 303
    assert unlocked.headers["location"].endswith(f"/public/artifact-share/{token}")
    cookie_name = unlock_cookie_name("artifact_share_unlock", token)
    unlock = share_client.cookies.get(cookie_name)
    assert unlock is not None

    # PRG: the followed GET authenticates via the unlock cookie. The cookie
    # path is the production /api/v1/... prefix while the test router mounts
    # under /public/artifact-share, so pass it explicitly like other tests.
    content = share_client.get(
        f"/public/artifact-share/{token}",
        headers={"Cookie": f"{cookie_name}={unlock}"},
        follow_redirects=False,
    )
    assert content.status_code == 200


@pytest.mark.asyncio
async def test_password_share_post_unlock_multi_file_redirects_to_index(share_client, html_artifact) -> None:
    """POST unlock of a multi-file share 303s to the trailing-slash index."""
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

    unlocked = share_client.post(
        f"/public/artifact-share/{token}",
        data={"p": "s3cret"},
        follow_redirects=False,
    )
    assert unlocked.status_code == 303
    assert unlocked.headers["location"].endswith(f"/{token}/")
    assert share_client.cookies.get(unlock_cookie_name("artifact_share_unlock", token)) is not None


@pytest.mark.asyncio
async def test_password_share_post_index_redirects_to_clean_index(share_client, html_artifact) -> None:
    """POST unlock on the trailing-slash index 303s to the same clean index."""
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

    unlocked = share_client.post(
        f"/public/artifact-share/{token}/",
        data={"p": "s3cret"},
        follow_redirects=False,
    )
    assert unlocked.status_code == 303
    assert unlocked.headers["location"].endswith(f"/{token}/")
    assert share_client.cookies.get(unlock_cookie_name("artifact_share_unlock", token)) is not None


@pytest.mark.asyncio
async def test_password_share_post_asset_unlock_redirects(share_client, html_artifact) -> None:
    """POST unlock on a static-asset URL 303s back to the clean asset GET."""
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

    unlocked = share_client.post(
        f"/public/artifact-share/{token}/styles.css",
        data={"p": "s3cret"},
        follow_redirects=False,
    )
    assert unlocked.status_code == 303
    assert unlocked.headers["location"].endswith(f"/{token}/styles.css")
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
async def test_password_share_post_wrong_password_gate(share_client, html_artifact) -> None:
    """A wrong password submitted via POST renders the gate again, never a 404."""
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

    gate = share_client.post(
        f"/public/artifact-share/{token}",
        data={"p": "wrong"},
        follow_redirects=False,
    )
    assert gate.status_code == 403
    assert "Incorrect password" in gate.text


@pytest.mark.asyncio
async def test_password_share_post_without_password_gate(share_client, html_artifact) -> None:
    """POST without a password renders the gate like a bare GET."""
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

    gate = share_client.post(f"/public/artifact-share/{token}", data={}, follow_redirects=False)
    assert gate.status_code == 403
    assert "Password Required" in gate.text


@pytest.mark.asyncio
async def test_password_share_post_short_remaining_serves_directly(share_client, html_artifact) -> None:
    """POST unlock with <60s remaining serves content instead of 303-looping.

    When the share is too close to expiry to issue an unlock cookie, a
    successful POST must not redirect to a GET that cannot authenticate (no
    cookie, no password) — that would loop back to the gate forever. The
    bundle is served directly so the current request always succeeds.
    """
    files = {
        "index.html": PublishFile(path="index.html", content="<html/>", encoding="utf-8"),
    }
    short_token = sign_share_token(
        {"aid": html_artifact.id, "vid": "short-version", "p": 1},
        salt="artifact-share",
        exp=int(time.time()) + 30,
        password="s3cret",
    )
    with patch(
        "app.services.artifacts.share.share_bundle.resolve_artifact_deploy_files",
        new_callable=AsyncMock,
        return_value=(html_artifact, files),
    ):
        unlocked = share_client.post(
            f"/public/artifact-share/{short_token}",
            data={"p": "s3cret"},
            follow_redirects=False,
        )
    assert unlocked.status_code == 200
    assert "text/html" in unlocked.headers["content-type"]
    assert "set-cookie" not in unlocked.headers
