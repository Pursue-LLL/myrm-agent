"""API tests for artifact share preview and public bundle routes."""

from __future__ import annotations

import shutil
import time
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI, HTTPException, Response
from fastapi.testclient import TestClient

from app.api.dependencies import get_workspace_root
from app.api.files.artifact_share_api import router as share_router
from app.api.files.artifact_share_public import (
    _HTML_MEDIA_TYPES,
    _SHARE_SECURITY_HEADERS,
    _attach_unlock_cookie,
    _build_unlock_credential,
    _file_response,
    _serve_share_bundle,
    _unlock_claims_from_cookie,
    _unlock_cookie_name,
    public_router,
)
from app.core.infra.limiter import limiter
from app.core.security.share_hmac import create_share_token
from app.database.connection import get_db
from app.database.models.artifact import Artifact, ArtifactVersion
from app.services.artifacts.share_bundle import (
    bundle_asset_count,
    bundle_dir_for_claims,
)
from app.services.artifacts.share_token import (
    ArtifactShareClaims,
    parse_artifact_share_token,
)
from app.services.hosting.packager import PublishFile


@pytest.fixture
def share_client(db_session, tmp_path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(
        "app.services.artifacts.share_bundle.settings.database.state_dir",
        str(tmp_path),
    )
    limiter.enabled = False
    test_app = FastAPI()
    test_app.include_router(share_router)
    test_app.include_router(public_router, prefix="/public/artifact-share")

    async def override_get_db():
        yield db_session

    async def override_workspace_root() -> str:
        return str(tmp_path)

    test_app.dependency_overrides[get_db] = override_get_db
    test_app.dependency_overrides[get_workspace_root] = override_workspace_root
    with TestClient(test_app) as test_client:
        yield test_client
    limiter.enabled = True


@pytest.fixture
async def html_artifact(db_session):
    artifact = Artifact(
        id=str(uuid.uuid4()),
        name="index.html",
        chat_id=str(uuid.uuid4()),
        is_deleted=False,
    )
    db_session.add(artifact)
    await db_session.commit()
    version = ArtifactVersion(
        id=str(uuid.uuid4()),
        artifact_id=artifact.id,
        vault_uri="vault://html",
        sha256_hash="hash",
    )
    db_session.add(version)
    await db_session.commit()
    await db_session.refresh(artifact)
    return artifact


@pytest.mark.asyncio
async def test_create_share_preview_materializes_bundle(
    share_client, html_artifact
) -> None:
    files = {
        "index.html": PublishFile(
            path="index.html", content="<html></html>", encoding="utf-8"
        ),
        "styles.css": PublishFile(
            path="styles.css", content="body{}", encoding="utf-8"
        ),
    }
    with patch(
        "app.services.artifacts.share_bundle.resolve_artifact_deploy_files",
        new_callable=AsyncMock,
        return_value=(html_artifact, files),
    ), patch(
        "app.api.files.artifact_share_api.get_public_ingress_base_url",
        new_callable=AsyncMock,
        return_value="",
    ):
        response = share_client.post(
            f"/{html_artifact.id}/share-preview",
            json={"ttl_days": 7, "artifact_type": "html"},
        )
    assert response.status_code == 200
    payload = response.json()
    token = payload["token"]
    claims = parse_artifact_share_token(token)
    assert claims is not None
    assert bundle_asset_count(claims) == 2
    assert payload["share_path"] == f"/api/v1/public/artifact-share/{token}"
    assert payload["share_url"] is None

    entry = share_client.get(f"/public/artifact-share/{token}", follow_redirects=False)
    assert entry.status_code == 307
    index = share_client.get(f"/public/artifact-share/{token}/", follow_redirects=False)
    assert index.status_code == 200

    css = share_client.get(f"/public/artifact-share/{token}/styles.css")
    assert css.status_code == 200
    assert "body" in css.text


@pytest.mark.asyncio
async def test_create_share_preview_exposes_absolute_share_url(
    share_client, html_artifact
) -> None:
    """Create response carries an absolute share_url when public ingress is set."""
    files = {
        "index.html": PublishFile(
            path="index.html", content="<html></html>", encoding="utf-8"
        ),
    }
    with patch(
        "app.services.artifacts.share_bundle.resolve_artifact_deploy_files",
        new_callable=AsyncMock,
        return_value=(html_artifact, files),
    ), patch(
        "app.api.files.artifact_share_api.get_public_ingress_base_url",
        new_callable=AsyncMock,
        return_value="https://myrm-x.example.com",
    ):
        response = share_client.post(
            f"/{html_artifact.id}/share-preview",
            json={"ttl_days": 7, "artifact_type": "html"},
        )
    assert response.status_code == 200
    payload = response.json()
    assert payload["share_url"] == (
        f"https://myrm-x.example.com{payload['share_path']}"
    )


@pytest.mark.asyncio
async def test_create_share_preview_share_url_falls_back_when_ingress_fails(
    share_client, html_artifact
) -> None:
    """Ingress resolution failure must not fail share creation (degrade to None)."""
    files = {
        "index.html": PublishFile(
            path="index.html", content="<html></html>", encoding="utf-8"
        ),
    }
    with patch(
        "app.services.artifacts.share_bundle.resolve_artifact_deploy_files",
        new_callable=AsyncMock,
        return_value=(html_artifact, files),
    ), patch(
        "app.api.files.artifact_share_api.get_public_ingress_base_url",
        new_callable=AsyncMock,
        side_effect=RuntimeError("ingress unavailable"),
    ):
        response = share_client.post(
            f"/{html_artifact.id}/share-preview",
            json={"ttl_days": 7, "artifact_type": "html"},
        )
    assert response.status_code == 200
    payload = response.json()
    assert payload["share_url"] is None


@pytest.mark.asyncio
async def test_html_share_includes_csp_headers(share_client, html_artifact) -> None:
    files = {
        "index.html": PublishFile(
            path="index.html", content="<html></html>", encoding="utf-8"
        ),
    }
    with patch(
        "app.services.artifacts.share_bundle.resolve_artifact_deploy_files",
        new_callable=AsyncMock,
        return_value=(html_artifact, files),
    ):
        response = share_client.post(
            f"/{html_artifact.id}/share-preview",
            json={"ttl_days": 7, "artifact_type": "html"},
        )
    token = response.json()["token"]
    index = share_client.get(f"/public/artifact-share/{token}", follow_redirects=False)
    assert index.status_code == 200
    csp = index.headers.get("content-security-policy", "")
    assert "default-src 'none'" in csp
    assert "'self'" in csp
    assert "connect-src 'none'" in csp
    assert index.headers.get("x-content-type-options") == "nosniff"
    assert index.headers.get("x-frame-options") == "DENY"
    assert index.headers.get("x-robots-tag") == "noindex, nofollow"
    assert index.headers.get("cache-control") == "no-store"


@pytest.mark.asyncio
async def test_pdf_share_omits_csp_headers(share_client, html_artifact) -> None:
    files = {
        "report.pdf": PublishFile(
            path="report.pdf", content="JVBERi0=", encoding="base64"
        ),
    }
    with patch(
        "app.services.artifacts.share_bundle.resolve_artifact_deploy_files",
        new_callable=AsyncMock,
        return_value=(html_artifact, files),
    ):
        response = share_client.post(
            f"/{html_artifact.id}/share-preview",
            json={"ttl_days": 7, "artifact_type": "pdf"},
        )
    token = response.json()["token"]
    entry = share_client.get(f"/public/artifact-share/{token}", follow_redirects=False)
    assert entry.status_code == 200
    assert "content-security-policy" not in entry.headers
    assert entry.headers.get("x-robots-tag") == "noindex, nofollow"
    assert entry.headers.get("cache-control") == "no-store"


@pytest.mark.asyncio
async def test_multi_file_bundle_csp_allows_self(share_client, html_artifact) -> None:
    """CSP 'self' allows same-origin CSS/JS in multi-file bundles."""
    files = {
        "index.html": PublishFile(
            path="index.html",
            content='<html><link href="styles.css"/></html>',
            encoding="utf-8",
        ),
        "styles.css": PublishFile(
            path="styles.css", content="body{}", encoding="utf-8"
        ),
    }
    with patch(
        "app.services.artifacts.share_bundle.resolve_artifact_deploy_files",
        new_callable=AsyncMock,
        return_value=(html_artifact, files),
    ):
        response = share_client.post(
            f"/{html_artifact.id}/share-preview",
            json={"ttl_days": 7, "artifact_type": "html"},
        )
    token = response.json()["token"]
    index = share_client.get(f"/public/artifact-share/{token}/", follow_redirects=False)
    csp = index.headers.get("content-security-policy", "")
    assert "script-src 'self' 'unsafe-inline'" in csp
    assert "style-src 'self' 'unsafe-inline'" in csp
    assert "img-src 'self' data: blob:" in csp

    css = share_client.get(f"/public/artifact-share/{token}/styles.css")
    assert css.status_code == 200
    assert "content-security-policy" not in css.headers
    assert css.headers.get("x-robots-tag") == "noindex, nofollow"
    assert css.headers.get("cache-control") == "no-store"


@pytest.mark.asyncio
async def test_create_share_preview_rejects_non_shareable(
    share_client, db_session
) -> None:
    artifact = Artifact(
        id=str(uuid.uuid4()),
        name="app.tsx",
        is_deleted=False,
    )
    db_session.add(artifact)
    await db_session.commit()
    response = share_client.post(
        f"/{artifact.id}/share-preview",
        json={"ttl_days": 7, "artifact_type": "code"},
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_public_share_invalid_token(share_client) -> None:
    response = share_client.get("/public/artifact-share/not-a-valid-token")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_single_file_share_serves_without_redirect(
    share_client, html_artifact
) -> None:
    files = {
        "report.pdf": PublishFile(
            path="report.pdf", content="JVBERi0=", encoding="base64"
        ),
    }
    with patch(
        "app.services.artifacts.share_bundle.resolve_artifact_deploy_files",
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
async def test_create_share_accepts_document_type_without_suffix(
    share_client, db_session
) -> None:
    artifact = Artifact(
        id=str(uuid.uuid4()),
        name="季度报告",
        is_deleted=False,
    )
    db_session.add(artifact)
    await db_session.commit()
    version = ArtifactVersion(
        id=str(uuid.uuid4()),
        artifact_id=artifact.id,
        vault_uri="vault://doc",
        sha256_hash="hash",
    )
    db_session.add(version)
    await db_session.commit()
    await db_session.refresh(artifact)

    files = {
        "季度报告": PublishFile(path="季度报告", content="# Title", encoding="utf-8"),
    }
    with patch(
        "app.services.artifacts.share_bundle.resolve_artifact_deploy_files",
        new_callable=AsyncMock,
        return_value=(artifact, files),
    ):
        response = share_client.post(
            f"/{artifact.id}/share-preview",
            json={"ttl_days": 7, "artifact_type": "document"},
        )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_create_share_artifact_not_found(share_client) -> None:
    response = share_client.post(
        f"/{uuid.uuid4()}/share-preview",
        json={"ttl_days": 7, "artifact_type": "html"},
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Artifact not found"


@pytest.mark.asyncio
async def test_create_share_no_versions(share_client, db_session) -> None:
    artifact = Artifact(id=str(uuid.uuid4()), name="index.html", is_deleted=False)
    db_session.add(artifact)
    await db_session.commit()
    response = share_client.post(
        f"/{artifact.id}/share-preview",
        json={"ttl_days": 7, "artifact_type": "html"},
    )
    assert response.status_code == 400
    assert "no versions" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_create_share_deleted_artifact(share_client, db_session) -> None:
    artifact = Artifact(
        id=str(uuid.uuid4()),
        name="index.html",
        is_deleted=True,
    )
    db_session.add(artifact)
    await db_session.commit()
    response = share_client.post(
        f"/{artifact.id}/share-preview",
        json={"ttl_days": 7, "artifact_type": "html"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_create_share_empty_files(share_client, html_artifact) -> None:
    with patch(
        "app.services.artifacts.share_bundle.resolve_artifact_deploy_files",
        new_callable=AsyncMock,
        return_value=(html_artifact, {}),
    ):
        response = share_client.post(
            f"/{html_artifact.id}/share-preview",
            json={"ttl_days": 7, "artifact_type": "html"},
        )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_create_share_ttl_out_of_range(share_client, html_artifact) -> None:
    response = share_client.post(
        f"/{html_artifact.id}/share-preview",
        json={"ttl_days": 31, "artifact_type": "html"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_public_share_expired_token(share_client, html_artifact) -> None:
    files = {
        "index.html": PublishFile(
            path="index.html", content="<html/>", encoding="utf-8"
        ),
    }
    with patch(
        "app.services.artifacts.share_bundle.resolve_artifact_deploy_files",
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
        "app.core.security.share_hmac.time.time",
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
        "app.services.artifacts.share_bundle.resolve_artifact_deploy_files",
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
        "index.html": PublishFile(
            path="index.html", content="<html/>", encoding="utf-8"
        ),
        "styles.css": PublishFile(
            path="styles.css", content="body{}", encoding="utf-8"
        ),
    }
    with patch(
        "app.services.artifacts.share_bundle.resolve_artifact_deploy_files",
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


@pytest.mark.asyncio
async def test_share_rematerialization_uses_pinned_version(
    share_client, html_artifact
) -> None:
    """Verify that bundle re-materialization passes version_id from JWT claims."""
    files_v1 = {
        "index.html": PublishFile(
            path="index.html", content="<html>v1</html>", encoding="utf-8"
        ),
    }
    with patch(
        "app.services.artifacts.share_bundle.resolve_artifact_deploy_files",
        new_callable=AsyncMock,
        return_value=(html_artifact, files_v1),
    ) as mock_resolve:
        response = share_client.post(
            f"/{html_artifact.id}/share-preview",
            json={"ttl_days": 7, "artifact_type": "html"},
        )
        assert response.status_code == 200
        assert mock_resolve.call_count == 1
        _, kwargs = mock_resolve.call_args
        assert "version_id" in kwargs
        assert kwargs["version_id"] is not None

    token = response.json()["token"]
    claims = parse_artifact_share_token(token)
    assert claims is not None

    assert bundle_asset_count(claims) == 1

    shutil.rmtree(bundle_dir_for_claims(claims), ignore_errors=True)
    assert bundle_asset_count(claims) == 0

    with patch(
        "app.services.artifacts.share_bundle.resolve_artifact_deploy_files",
        new_callable=AsyncMock,
        return_value=(html_artifact, files_v1),
    ) as mock_resolve_again:
        serve = share_client.get(
            f"/public/artifact-share/{token}", follow_redirects=False
        )
        assert serve.status_code == 200
        _, kwargs2 = mock_resolve_again.call_args
        assert kwargs2["version_id"] == claims.version_id


@pytest.mark.asyncio
async def test_share_version_pinning_integration(
    share_client, db_session, tmp_path
) -> None:
    """Integration: full share→delete→re-materialize chain with real vault, no key-path mocks."""
    from myrm_agent_harness.agent.artifacts.vault import ArtifactVault

    vault = ArtifactVault(str(tmp_path))
    v1_uri = vault.put("<html>v1</html>", "index.html")
    v2_uri = vault.put("<html>v2-latest</html>", "index.html")

    artifact = Artifact(
        id=str(uuid.uuid4()),
        name="index.html",
        chat_id=str(uuid.uuid4()),
        is_deleted=False,
    )
    db_session.add(artifact)
    await db_session.commit()

    ver1 = ArtifactVersion(
        id=str(uuid.uuid4()),
        artifact_id=artifact.id,
        vault_uri=v1_uri,
        sha256_hash="h1",
    )
    db_session.add(ver1)
    await db_session.commit()

    import asyncio

    await asyncio.sleep(0.05)

    ver2 = ArtifactVersion(
        id=str(uuid.uuid4()),
        artifact_id=artifact.id,
        vault_uri=v2_uri,
        sha256_hash="h2",
    )
    db_session.add(ver2)
    await db_session.commit()
    await db_session.refresh(artifact)

    with patch(
        "app.services.hosting.artifact_files.ensure_artifact_for_deploy",
        new_callable=AsyncMock,
        return_value=artifact,
    ):
        response = share_client.post(
            f"/{artifact.id}/share-preview",
            json={"ttl_days": 7, "artifact_type": "html"},
        )
    assert response.status_code == 200
    payload = response.json()
    assert payload["version_id"] == ver2.id

    token = payload["token"]
    claims = parse_artifact_share_token(token)
    assert claims is not None

    first_serve = share_client.get(
        f"/public/artifact-share/{token}", follow_redirects=False
    )
    assert first_serve.status_code == 200
    assert "v2-latest" in first_serve.text

    shutil.rmtree(bundle_dir_for_claims(claims), ignore_errors=True)
    assert bundle_asset_count(claims) == 0

    with patch(
        "app.services.hosting.artifact_files.ensure_artifact_for_deploy",
        new_callable=AsyncMock,
        return_value=artifact,
    ):
        re_serve = share_client.get(
            f"/public/artifact-share/{token}", follow_redirects=False
        )
    assert re_serve.status_code == 200
    assert "v2-latest" in re_serve.text


@pytest.mark.asyncio
async def test_share_pinned_version_survives_new_version(
    share_client, db_session, tmp_path
) -> None:
    """Share pins v1, then v2 is added; re-materialization still serves v1 content."""
    from datetime import datetime, timedelta

    from myrm_agent_harness.agent.artifacts.vault import ArtifactVault

    vault = ArtifactVault(str(tmp_path))
    v1_uri = vault.put("<html>v1-pinned</html>", "index.html")

    art_id = str(uuid.uuid4())
    chat_id = str(uuid.uuid4())
    t1 = datetime(2025, 1, 1)

    artifact = Artifact(id=art_id, name="index.html", chat_id=chat_id, is_deleted=False)
    db_session.add(artifact)
    await db_session.commit()

    ver1 = ArtifactVersion(
        id=str(uuid.uuid4()),
        artifact_id=art_id,
        vault_uri=v1_uri,
        sha256_hash="h1",
    )
    db_session.add(ver1)
    await db_session.commit()
    await db_session.refresh(artifact)

    detached_v1_only = _make_detached_artifact(
        artifact_id=art_id,
        name="index.html",
        chat_id=chat_id,
        versions=[ver1],
    )
    with patch(
        "app.services.hosting.artifact_files.ensure_artifact_for_deploy",
        new_callable=AsyncMock,
        return_value=detached_v1_only,
    ):
        response = share_client.post(
            f"/{artifact.id}/share-preview",
            json={"ttl_days": 7, "artifact_type": "html"},
        )
    assert response.status_code == 200
    assert response.json()["version_id"] == ver1.id
    token = response.json()["token"]

    v2_uri = vault.put("<html>v2-newer</html>", "index.html")
    ver2 = ArtifactVersion(
        id=str(uuid.uuid4()),
        artifact_id=art_id,
        vault_uri=v2_uri,
        sha256_hash="h2",
        created_at=t1 + timedelta(hours=1),
    )
    db_session.add(ver2)
    await db_session.commit()

    claims = parse_artifact_share_token(token)
    assert claims is not None
    shutil.rmtree(bundle_dir_for_claims(claims), ignore_errors=True)

    detached_both = _make_detached_artifact(
        artifact_id=art_id,
        name="index.html",
        chat_id=chat_id,
        versions=[ver1, ver2],
    )
    with patch(
        "app.services.hosting.artifact_files.ensure_artifact_for_deploy",
        new_callable=AsyncMock,
        return_value=detached_both,
    ):
        re_serve = share_client.get(
            f"/public/artifact-share/{token}", follow_redirects=False
        )
    assert re_serve.status_code == 200
    assert "v1-pinned" in re_serve.text
    assert "v2-newer" not in re_serve.text


@pytest.mark.asyncio
async def test_share_invalid_version_returns_404(
    share_client, db_session, tmp_path
) -> None:
    """Re-materialization with a deleted/invalid version_id returns 404."""
    from myrm_agent_harness.agent.artifacts.vault import ArtifactVault

    vault = ArtifactVault(str(tmp_path))
    v1_uri = vault.put("<html>v1</html>", "index.html")

    artifact = Artifact(
        id=str(uuid.uuid4()),
        name="index.html",
        chat_id=str(uuid.uuid4()),
        is_deleted=False,
    )
    db_session.add(artifact)
    await db_session.commit()
    ver1 = ArtifactVersion(
        id=str(uuid.uuid4()),
        artifact_id=artifact.id,
        vault_uri=v1_uri,
        sha256_hash="h1",
    )
    db_session.add(ver1)
    await db_session.commit()
    await db_session.refresh(artifact)

    with patch(
        "app.services.hosting.artifact_files.ensure_artifact_for_deploy",
        new_callable=AsyncMock,
        return_value=artifact,
    ):
        response = share_client.post(
            f"/{artifact.id}/share-preview",
            json={"ttl_days": 7, "artifact_type": "html"},
        )
    assert response.status_code == 200
    token = response.json()["token"]

    claims = parse_artifact_share_token(token)
    assert claims is not None
    shutil.rmtree(bundle_dir_for_claims(claims), ignore_errors=True)

    artifact_no_ver = Artifact(
        id=artifact.id, name="index.html", chat_id=artifact.chat_id, is_deleted=False
    )
    artifact_no_ver.versions = []

    with patch(
        "app.services.hosting.artifact_files.ensure_artifact_for_deploy",
        new_callable=AsyncMock,
        return_value=artifact_no_ver,
    ):
        re_serve = share_client.get(
            f"/public/artifact-share/{token}", follow_redirects=False
        )
    assert re_serve.status_code == 404


def _make_detached_artifact(*, artifact_id, name, chat_id, versions):
    """Build a detached Artifact with eagerly-set versions (no lazy load)."""
    a = Artifact(id=artifact_id, name=name, chat_id=chat_id, is_deleted=False)
    a.versions = list(versions)
    return a


@pytest.mark.asyncio
async def test_resolve_artifact_deploy_files_version_id_none_uses_latest(
    db_session, tmp_path
) -> None:
    """When version_id=None, resolve_artifact_deploy_files picks the latest version."""
    from datetime import datetime, timedelta

    from myrm_agent_harness.agent.artifacts.vault import ArtifactVault

    from app.services.hosting.artifact_files import resolve_artifact_deploy_files

    vault = ArtifactVault(str(tmp_path))
    v1_uri = vault.put("<html>old</html>", "index.html")
    v2_uri = vault.put("<html>new-latest</html>", "index.html")

    art_id = str(uuid.uuid4())
    chat_id = str(uuid.uuid4())
    t1 = datetime(2025, 1, 1)
    t2 = t1 + timedelta(hours=1)

    ver1 = ArtifactVersion(
        id=str(uuid.uuid4()),
        artifact_id=art_id,
        vault_uri=v1_uri,
        sha256_hash="h1",
        created_at=t1,
    )
    ver2 = ArtifactVersion(
        id=str(uuid.uuid4()),
        artifact_id=art_id,
        vault_uri=v2_uri,
        sha256_hash="h2",
        created_at=t2,
    )

    detached = _make_detached_artifact(
        artifact_id=art_id, name="index.html", chat_id=chat_id, versions=[ver1, ver2]
    )

    with patch(
        "app.services.hosting.artifact_files.ensure_artifact_for_deploy",
        new_callable=AsyncMock,
        return_value=detached,
    ):
        _, files = await resolve_artifact_deploy_files(
            db_session, art_id, str(tmp_path)
        )

    import base64

    raw = next(iter(files.values())).content
    decoded = (
        base64.b64decode(raw).decode() if ";" not in raw and "/" not in raw else raw
    )
    assert "new-latest" in decoded


@pytest.mark.asyncio
async def test_resolve_artifact_deploy_files_explicit_version(
    db_session, tmp_path
) -> None:
    """When version_id is given, resolve_artifact_deploy_files picks that exact version."""
    from datetime import datetime, timedelta

    from myrm_agent_harness.agent.artifacts.vault import ArtifactVault

    from app.services.hosting.artifact_files import resolve_artifact_deploy_files

    vault = ArtifactVault(str(tmp_path))
    v1_uri = vault.put("<html>first</html>", "index.html")
    v2_uri = vault.put("<html>second</html>", "index.html")

    art_id = str(uuid.uuid4())
    chat_id = str(uuid.uuid4())
    t1 = datetime(2025, 1, 1)
    t2 = t1 + timedelta(hours=1)

    ver1 = ArtifactVersion(
        id=str(uuid.uuid4()),
        artifact_id=art_id,
        vault_uri=v1_uri,
        sha256_hash="h1",
        created_at=t1,
    )
    ver2 = ArtifactVersion(
        id=str(uuid.uuid4()),
        artifact_id=art_id,
        vault_uri=v2_uri,
        sha256_hash="h2",
        created_at=t2,
    )

    detached = _make_detached_artifact(
        artifact_id=art_id, name="index.html", chat_id=chat_id, versions=[ver1, ver2]
    )

    with patch(
        "app.services.hosting.artifact_files.ensure_artifact_for_deploy",
        new_callable=AsyncMock,
        return_value=detached,
    ):
        _, files_v1 = await resolve_artifact_deploy_files(
            db_session, art_id, str(tmp_path), version_id=ver1.id
        )
    raw_v1 = next(iter(files_v1.values())).content
    # Vault object is extension-less but named from artifact.name (index.html),
    # so the HTML payload is stored as UTF-8 text rather than base64.
    assert "first" in raw_v1

    with patch(
        "app.services.hosting.artifact_files.ensure_artifact_for_deploy",
        new_callable=AsyncMock,
        return_value=detached,
    ):
        _, files_v2 = await resolve_artifact_deploy_files(
            db_session, art_id, str(tmp_path), version_id=ver2.id
        )
    raw_v2 = next(iter(files_v2.values())).content
    assert "second" in raw_v2


@pytest.mark.asyncio
async def test_resolve_artifact_deploy_files_invalid_version_raises(
    db_session, tmp_path
) -> None:
    """When version_id doesn't match any version, LookupError is raised."""
    from myrm_agent_harness.agent.artifacts.vault import ArtifactVault

    from app.services.hosting.artifact_files import resolve_artifact_deploy_files

    vault = ArtifactVault(str(tmp_path))
    v1_uri = vault.put("<html>only</html>", "index.html")

    art_id = str(uuid.uuid4())
    ver1 = ArtifactVersion(
        id=str(uuid.uuid4()), artifact_id=art_id, vault_uri=v1_uri, sha256_hash="h1"
    )
    detached = _make_detached_artifact(
        artifact_id=art_id,
        name="index.html",
        chat_id=str(uuid.uuid4()),
        versions=[ver1],
    )

    with patch(
        "app.services.hosting.artifact_files.ensure_artifact_for_deploy",
        new_callable=AsyncMock,
        return_value=detached,
    ):
        with pytest.raises(LookupError, match="not found"):
            await resolve_artifact_deploy_files(
                db_session, art_id, str(tmp_path), version_id="nonexistent-id"
            )


@pytest.mark.asyncio
async def test_create_share_rejects_ambiguous_multi_html(
    share_client, html_artifact
) -> None:
    files = {
        "a.html": PublishFile(path="a.html", content="<html/>", encoding="utf-8"),
        "b.html": PublishFile(path="b.html", content="<html/>", encoding="utf-8"),
    }
    with patch(
        "app.services.artifacts.share_bundle.resolve_artifact_deploy_files",
        new_callable=AsyncMock,
        return_value=(html_artifact, files),
    ):
        response = share_client.post(
            f"/{html_artifact.id}/share-preview",
            json={"ttl_days": 7, "artifact_type": "html"},
        )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_csp_integration_html_real_vault(
    share_client, db_session, tmp_path
) -> None:
    """Integration: real Vault → create share → public GET → CSP headers present."""
    from myrm_agent_harness.agent.artifacts.vault import ArtifactVault

    vault = ArtifactVault(str(tmp_path))
    uri = vault.put("<html><body>hello</body></html>", "index.html")

    artifact = Artifact(
        id=str(uuid.uuid4()),
        name="index.html",
        chat_id=str(uuid.uuid4()),
        is_deleted=False,
    )
    db_session.add(artifact)
    await db_session.commit()
    ver = ArtifactVersion(
        id=str(uuid.uuid4()),
        artifact_id=artifact.id,
        vault_uri=uri,
        sha256_hash="h_csp",
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
            json={"ttl_days": 7, "artifact_type": "html"},
        )
    assert resp.status_code == 200
    token = resp.json()["token"]

    serve = share_client.get(f"/public/artifact-share/{token}", follow_redirects=False)
    assert serve.status_code == 200
    csp = serve.headers.get("content-security-policy", "")
    assert "default-src 'none'" in csp
    assert "script-src 'self' 'unsafe-inline'" in csp
    assert "connect-src 'none'" in csp
    assert serve.headers.get("x-content-type-options") == "nosniff"
    assert serve.headers.get("x-frame-options") == "DENY"


@pytest.mark.asyncio
async def test_csp_integration_multi_file_bundle(
    share_client, db_session, tmp_path
) -> None:
    """Integration: multi-file bundle with real Vault → CSP on HTML, no CSP on CSS asset."""
    from myrm_agent_harness.agent.artifacts.vault import ArtifactVault

    vault = ArtifactVault(str(tmp_path))
    uri = vault.put(
        '<html><link rel="stylesheet" href="style.css"/><body>test</body></html>',
        "index.html",
    )

    artifact = Artifact(
        id=str(uuid.uuid4()),
        name="index.html",
        chat_id=str(uuid.uuid4()),
        is_deleted=False,
    )
    db_session.add(artifact)
    await db_session.commit()
    ver = ArtifactVersion(
        id=str(uuid.uuid4()),
        artifact_id=artifact.id,
        vault_uri=uri,
        sha256_hash="h_multi",
    )
    db_session.add(ver)
    await db_session.commit()
    await db_session.refresh(artifact)

    detached = _make_detached_artifact(
        artifact_id=artifact.id,
        name="index.html",
        chat_id=artifact.chat_id,
        versions=[ver],
    )
    with patch(
        "app.services.hosting.artifact_files.ensure_artifact_for_deploy",
        new_callable=AsyncMock,
        return_value=detached,
    ):
        resp = share_client.post(
            f"/{artifact.id}/share-preview",
            json={"ttl_days": 7, "artifact_type": "html"},
        )
    assert resp.status_code == 200
    token = resp.json()["token"]

    index_resp = share_client.get(
        f"/public/artifact-share/{token}",
        follow_redirects=False,
    )
    assert index_resp.status_code == 200
    csp = index_resp.headers.get("content-security-policy", "")
    assert "style-src 'self' 'unsafe-inline'" in csp
    assert "img-src 'self' data: blob:" in csp


@pytest.mark.asyncio
async def test_csp_integration_pdf_real_vault(
    share_client, db_session, tmp_path
) -> None:
    """Integration: real Vault PDF → public GET → correct media type + no HTML headers.

    Vault objects are extension-less UUID files; the entry name now derives
    from artifact.name (report.pdf), so a PDF is served as ``application/pdf``
    and deliberately omits the HTML-only security headers (CSP/nosniff).
    """
    from myrm_agent_harness.agent.artifacts.vault import ArtifactVault

    vault = ArtifactVault(str(tmp_path))
    uri = vault.put("%PDF-1.4 dummy", "report.pdf")

    artifact = Artifact(
        id=str(uuid.uuid4()),
        name="report.pdf",
        chat_id=str(uuid.uuid4()),
        is_deleted=False,
    )
    db_session.add(artifact)
    await db_session.commit()
    ver = ArtifactVersion(
        id=str(uuid.uuid4()),
        artifact_id=artifact.id,
        vault_uri=uri,
        sha256_hash="h_pdf",
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
            json={"ttl_days": 7, "artifact_type": "pdf"},
        )
    assert resp.status_code == 200
    token = resp.json()["token"]

    serve = share_client.get(f"/public/artifact-share/{token}", follow_redirects=False)
    assert serve.status_code == 200
    assert serve.headers["content-type"].startswith("application/pdf")
    assert serve.headers.get("x-content-type-options") is None


@pytest.mark.asyncio
async def test_password_share_unlock_cookie_keeps_extensionless_media_type(
    share_client, db_session, tmp_path
) -> None:
    """R1: unlock-cookie auth keeps artifact_type for extension-less PDF entries.

    A password share of a PDF whose artifact name has no suffix (entry file has
    no extension) must still be served as ``application/pdf`` when the browser
    refreshes and authenticates via the unlock cookie instead of ``p``.
    """
    from myrm_agent_harness.agent.artifacts.vault import ArtifactVault

    vault = ArtifactVault(str(tmp_path))
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

    first = share_client.get(
        f"/public/artifact-share/{token}?p=s3cret", follow_redirects=False
    )
    assert first.status_code == 200
    assert first.headers["content-type"].startswith("application/pdf")
    cookie_name = _unlock_cookie_name(token)
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


# ---------------------------------------------------------------------------
# _file_response unit tests (direct function, no HTTP)
# ---------------------------------------------------------------------------


class TestFileResponseCSP:
    """Exhaustive _file_response media_type → header boundary tests."""

    def _make_tmp_file(self, tmp_path: Path) -> str:
        p = tmp_path / "test_file"
        p.write_text("content")
        return str(p)

    def test_html_media_type_has_csp(self, tmp_path: Path) -> None:
        path = self._make_tmp_file(tmp_path)
        resp = _file_response(path, "text/html", "index.html")
        assert resp.headers.get("content-security-policy") is not None

    def test_html_charset_has_csp(self, tmp_path: Path) -> None:
        path = self._make_tmp_file(tmp_path)
        resp = _file_response(path, "text/html; charset=utf-8", "index.html")
        assert resp.headers.get("content-security-policy") is not None

    def test_xhtml_has_csp(self, tmp_path: Path) -> None:
        path = self._make_tmp_file(tmp_path)
        resp = _file_response(path, "application/xhtml+xml", "page.xhtml")
        assert resp.headers.get("content-security-policy") is not None

    def test_css_no_csp(self, tmp_path: Path) -> None:
        path = self._make_tmp_file(tmp_path)
        resp = _file_response(path, "text/css", "style.css")
        assert resp.headers.get("content-security-policy") is None

    def test_javascript_no_csp(self, tmp_path: Path) -> None:
        path = self._make_tmp_file(tmp_path)
        resp = _file_response(path, "application/javascript", "app.js")
        assert resp.headers.get("content-security-policy") is None

    def test_pdf_no_csp(self, tmp_path: Path) -> None:
        path = self._make_tmp_file(tmp_path)
        resp = _file_response(path, "application/pdf", "report.pdf")
        assert resp.headers.get("content-security-policy") is None

    def test_octet_stream_no_csp(self, tmp_path: Path) -> None:
        path = self._make_tmp_file(tmp_path)
        resp = _file_response(path, "application/octet-stream", "data.bin")
        assert resp.headers.get("content-security-policy") is None

    def test_plain_text_no_csp(self, tmp_path: Path) -> None:
        path = self._make_tmp_file(tmp_path)
        resp = _file_response(path, "text/plain", "readme.txt")
        assert resp.headers.get("content-security-policy") is None


class TestFileResponsePrivacyHeaders:
    """Privacy headers (noindex + no-store) apply to every served file type."""

    def _make_tmp_file(self, tmp_path: Path) -> str:
        p = tmp_path / "test_file"
        p.write_text("content")
        return str(p)

    @pytest.mark.parametrize(
        "media_type",
        [
            "text/html",
            "text/html; charset=utf-8",
            "application/xhtml+xml",
            "text/css",
            "application/javascript",
            "application/pdf",
            "text/plain",
            "application/octet-stream",
        ],
    )
    def test_privacy_headers_present_for_all_media_types(
        self, tmp_path: Path, media_type: str
    ) -> None:
        path = self._make_tmp_file(tmp_path)
        resp = _file_response(path, media_type, "file")
        assert resp.headers.get("x-robots-tag") == "noindex, nofollow"
        assert resp.headers.get("cache-control") == "no-store"


class TestShareSecurityHeadersCompleteness:
    """Verify _SHARE_SECURITY_HEADERS constant has exact expected directives."""

    def test_csp_has_all_nine_directives(self) -> None:
        csp = _SHARE_SECURITY_HEADERS["Content-Security-Policy"]
        expected = [
            "default-src 'none'",
            "script-src 'self' 'unsafe-inline'",
            "style-src 'self' 'unsafe-inline'",
            "img-src 'self' data: blob:",
            "font-src 'self' data:",
            "media-src 'self' data: blob:",
            "connect-src 'none'",
            "frame-src 'none'",
            "object-src 'none'",
        ]
        for directive in expected:
            assert directive in csp, f"Missing CSP directive: {directive}"

    def test_x_content_type_options(self) -> None:
        assert _SHARE_SECURITY_HEADERS["X-Content-Type-Options"] == "nosniff"

    def test_x_frame_options(self) -> None:
        assert _SHARE_SECURITY_HEADERS["X-Frame-Options"] == "DENY"

    def test_html_media_types_coverage(self) -> None:
        assert "text/html" in _HTML_MEDIA_TYPES
        assert "text/html; charset=utf-8" in _HTML_MEDIA_TYPES
        assert "application/xhtml+xml" in _HTML_MEDIA_TYPES
        assert len(_HTML_MEDIA_TYPES) == 3


@pytest.mark.asyncio
async def test_multi_file_redirect_has_no_csp(share_client, html_artifact) -> None:
    """307 redirect for multi-file bundles must not carry CSP headers."""
    files = {
        "index.html": PublishFile(
            path="index.html", content="<html/>", encoding="utf-8"
        ),
        "app.js": PublishFile(
            path="app.js", content="console.log(1)", encoding="utf-8"
        ),
    }
    with patch(
        "app.services.artifacts.share_bundle.resolve_artifact_deploy_files",
        new_callable=AsyncMock,
        return_value=(html_artifact, files),
    ):
        response = share_client.post(
            f"/{html_artifact.id}/share-preview",
            json={"ttl_days": 7, "artifact_type": "html"},
        )
    token = response.json()["token"]
    redirect = share_client.get(
        f"/public/artifact-share/{token}", follow_redirects=False
    )
    assert redirect.status_code == 307
    assert "content-security-policy" not in redirect.headers
    # Redirect is transient; the followed target carries privacy headers itself.
    assert "x-robots-tag" not in redirect.headers
    assert "cache-control" not in redirect.headers


@pytest.mark.asyncio
async def test_nested_css_asset_no_csp(share_client, html_artifact) -> None:
    """CSS sub-asset in nested path must not carry CSP headers."""
    files = {
        "index.html": PublishFile(
            path="index.html",
            content='<html><link href="assets/main.css"/></html>',
            encoding="utf-8",
        ),
        "assets/main.css": PublishFile(
            path="assets/main.css", content=".a{}", encoding="utf-8"
        ),
    }
    with patch(
        "app.services.artifacts.share_bundle.resolve_artifact_deploy_files",
        new_callable=AsyncMock,
        return_value=(html_artifact, files),
    ):
        response = share_client.post(
            f"/{html_artifact.id}/share-preview",
            json={"ttl_days": 7, "artifact_type": "html"},
        )
    token = response.json()["token"]
    css = share_client.get(f"/public/artifact-share/{token}/assets/main.css")
    assert css.status_code == 200
    assert "content-security-policy" not in css.headers
    assert css.headers.get("x-content-type-options") is None
    assert css.headers.get("x-robots-tag") == "noindex, nofollow"
    assert css.headers.get("cache-control") == "no-store"


@pytest.mark.asyncio
async def test_password_share_redirect_preserves_query(
    share_client, html_artifact
) -> None:
    """307 redirect for multi-file password shares must keep the ``p`` query."""
    files = {
        "index.html": PublishFile(
            path="index.html",
            content='<html><link href="styles.css"/></html>',
            encoding="utf-8",
        ),
        "styles.css": PublishFile(
            path="styles.css", content="body{}", encoding="utf-8"
        ),
    }
    with patch(
        "app.services.artifacts.share_bundle.resolve_artifact_deploy_files",
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
    assert share_client.cookies.get(_unlock_cookie_name(token)) is not None


@pytest.mark.asyncio
async def test_password_share_asset_requires_credential(
    share_client, html_artifact
) -> None:
    """Static assets of a password-protected share are gated without credentials."""
    files = {
        "index.html": PublishFile(
            path="index.html", content="<html/>", encoding="utf-8"
        ),
        "styles.css": PublishFile(
            path="styles.css", content="body{}", encoding="utf-8"
        ),
    }
    with patch(
        "app.services.artifacts.share_bundle.resolve_artifact_deploy_files",
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
async def test_password_share_asset_served_after_unlock(
    share_client, html_artifact
) -> None:
    """Once unlocked via ``p``, the unlock cookie authorizes static assets."""
    files = {
        "index.html": PublishFile(
            path="index.html",
            content='<html><link href="styles.css"/></html>',
            encoding="utf-8",
        ),
        "styles.css": PublishFile(
            path="styles.css", content="body{}", encoding="utf-8"
        ),
    }
    with patch(
        "app.services.artifacts.share_bundle.resolve_artifact_deploy_files",
        new_callable=AsyncMock,
        return_value=(html_artifact, files),
    ):
        response = share_client.post(
            f"/{html_artifact.id}/share-preview",
            json={"ttl_days": 7, "artifact_type": "html", "password": "s3cret"},
        )
    token = response.json()["token"]
    entry = share_client.get(
        f"/public/artifact-share/{token}/?p=s3cret", follow_redirects=False
    )
    assert entry.status_code == 200
    cookie_name = _unlock_cookie_name(token)
    unlock = share_client.cookies.get(cookie_name)
    assert unlock is not None

    asset = share_client.get(
        f"/public/artifact-share/{token}/styles.css",
        headers={"Cookie": f"{cookie_name}={unlock}"},
    )
    assert asset.status_code == 200
    assert "body" in asset.text


@pytest.mark.asyncio
async def test_password_single_file_share_serves_without_redirect(
    share_client, html_artifact
) -> None:
    """Single-file password shares keep serving inline with a Set-Cookie unlock."""
    files = {
        "index.html": PublishFile(
            path="index.html", content="<html/>", encoding="utf-8"
        ),
    }
    with patch(
        "app.services.artifacts.share_bundle.resolve_artifact_deploy_files",
        new_callable=AsyncMock,
        return_value=(html_artifact, files),
    ):
        response = share_client.post(
            f"/{html_artifact.id}/share-preview",
            json={"ttl_days": 7, "artifact_type": "html", "password": "s3cret"},
        )
    token = response.json()["token"]
    entry = share_client.get(
        f"/public/artifact-share/{token}?p=s3cret", follow_redirects=False
    )
    assert entry.status_code == 200
    assert "set-cookie" in entry.headers
    assert share_client.cookies.get(_unlock_cookie_name(token)) is not None


@pytest.mark.asyncio
async def test_password_share_wrong_password_gate(share_client, html_artifact) -> None:
    """A wrong password renders the password gate again, never a 404."""
    files = {
        "index.html": PublishFile(
            path="index.html", content="<html/>", encoding="utf-8"
        ),
    }
    with patch(
        "app.services.artifacts.share_bundle.resolve_artifact_deploy_files",
        new_callable=AsyncMock,
        return_value=(html_artifact, files),
    ):
        response = share_client.post(
            f"/{html_artifact.id}/share-preview",
            json={"ttl_days": 7, "artifact_type": "html", "password": "s3cret"},
        )
    token = response.json()["token"]
    gate = share_client.get(
        f"/public/artifact-share/{token}?p=wrong", follow_redirects=False
    )
    assert gate.status_code == 403
    assert "Incorrect password" in gate.text


@pytest.mark.asyncio
async def test_password_shares_use_independent_cookies(
    share_client, html_artifact, db_session
) -> None:
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
        "styles.css": PublishFile(
            path="styles.css", content="body{}", encoding="utf-8"
        ),
    }
    with patch(
        "app.services.artifacts.share_bundle.resolve_artifact_deploy_files",
        new_callable=AsyncMock,
        return_value=(html_artifact, files),
    ):
        first = share_client.post(
            f"/{html_artifact.id}/share-preview",
            json={"ttl_days": 7, "artifact_type": "html", "password": "s3cret"},
        )
    with patch(
        "app.services.artifacts.share_bundle.resolve_artifact_deploy_files",
        new_callable=AsyncMock,
        return_value=(second_artifact, files),
    ):
        second = share_client.post(
            f"/{second_artifact.id}/share-preview",
            json={"ttl_days": 7, "artifact_type": "html", "password": "s3cret"},
        )
    first_token = first.json()["token"]
    second_token = second.json()["token"]
    assert _unlock_cookie_name(first_token) != _unlock_cookie_name(second_token)

    first_entry = share_client.get(
        f"/public/artifact-share/{first_token}/?p=s3cret", follow_redirects=False
    )
    assert first_entry.status_code == 200
    first_unlock = share_client.cookies.get(_unlock_cookie_name(first_token))
    assert first_unlock is not None

    second_entry = share_client.get(
        f"/public/artifact-share/{second_token}/?p=s3cret", follow_redirects=False
    )
    assert second_entry.status_code == 200

    first_asset = share_client.get(
        f"/public/artifact-share/{first_token}/styles.css",
        headers={"Cookie": f"{_unlock_cookie_name(first_token)}={first_unlock}"},
    )
    assert first_asset.status_code == 200
    assert "body" in first_asset.text


def test_unlock_credential_rejects_short_remaining() -> None:
    """No unlock cookie is issued when the share is about to expire."""
    claims = ArtifactShareClaims(
        artifact_id="a", version_id="v", exp=int(time.time()) + 30
    )
    assert _build_unlock_credential(claims) is None


def test_unlock_credential_roundtrip() -> None:
    """A valid credential round-trips through claims recovery."""
    claims = ArtifactShareClaims(
        artifact_id="a", version_id="v", exp=int(time.time()) + 3600
    )
    credential = _build_unlock_credential(claims)
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
    credential = _build_unlock_credential(claims)
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
    claims = ArtifactShareClaims(
        artifact_id="a", version_id="v", exp=int(time.time()) + 30
    )
    _attach_unlock_cookie(response, claims, "token", "pw", secure=False)
    assert "set-cookie" not in response.headers


@pytest.mark.parametrize(
    ("exc", "status"),
    [
        (ValueError("boom"), 400),
        (LookupError("gone"), 404),
        (FileNotFoundError("gone"), 404),
    ],
)
@pytest.mark.asyncio
async def test_create_share_materialize_error_mapping(
    share_client, html_artifact, exc: Exception, status: int
) -> None:
    with patch(
        "app.api.files.artifact_share_api.materialize_share_bundle",
        new_callable=AsyncMock,
        side_effect=exc,
    ):
        response = share_client.post(
            f"/{html_artifact.id}/share-preview",
            json={"ttl_days": 7, "artifact_type": "html"},
        )
    assert response.status_code == status


@pytest.mark.asyncio
async def test_password_share_index_gate_without_password(
    share_client, html_artifact
) -> None:
    """A password-protected multi-file share's index is gated without ``p``."""
    files = {
        "index.html": PublishFile(
            path="index.html", content="<html/>", encoding="utf-8"
        ),
    }
    with patch(
        "app.services.artifacts.share_bundle.resolve_artifact_deploy_files",
        new_callable=AsyncMock,
        return_value=(html_artifact, files),
    ):
        response = share_client.post(
            f"/{html_artifact.id}/share-preview",
            json={"ttl_days": 7, "artifact_type": "html", "password": "s3cret"},
        )
    token = response.json()["token"]
    gate = share_client.get(
        f"/public/artifact-share/{token}/", follow_redirects=False
    )
    assert gate.status_code == 403
    assert "password" in gate.text.lower()


@pytest.mark.parametrize(
    ("exc", "status"),
    [
        (LookupError("gone"), 404),
        (FileNotFoundError("gone"), 404),
        (RuntimeError("boom"), 500),
    ],
)
@pytest.mark.asyncio
async def test_serve_bundle_materialize_error_mapping(
    share_client, exc: Exception, status: int
) -> None:
    claims = ArtifactShareClaims(
        artifact_id="a", version_id="v", exp=int(time.time()) + 3600
    )
    with patch(
        "app.api.files.artifact_share_public.resolve_share_bundle_file",
        return_value=None,
    ), patch(
        "app.api.files.artifact_share_public.materialize_share_bundle",
        new_callable=AsyncMock,
        side_effect=exc,
    ):
        with pytest.raises(HTTPException) as exc_info:
            await _serve_share_bundle(claims, None, "/tmp", None)
    assert exc_info.value.status_code == status


@pytest.mark.asyncio
async def test_serve_bundle_missing_after_materialize(share_client) -> None:
    """A bundle that still resolves to nothing after materialize is a 404."""
    claims = ArtifactShareClaims(
        artifact_id="a", version_id="v", exp=int(time.time()) + 3600
    )
    with patch(
        "app.api.files.artifact_share_public.resolve_share_bundle_file",
        return_value=None,
    ), patch(
        "app.api.files.artifact_share_public.materialize_share_bundle",
        new_callable=AsyncMock,
    ):
        with pytest.raises(HTTPException) as exc_info:
            await _serve_share_bundle(claims, None, "/tmp", None)
    assert exc_info.value.status_code == 404
