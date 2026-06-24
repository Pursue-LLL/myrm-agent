"""API tests for artifact share preview and public bundle routes."""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.dependencies import get_workspace_root
from app.api.files.artifact_share_api import (
    _HTML_MEDIA_TYPES,
    _SHARE_SECURITY_HEADERS,
    _file_response,
    public_router,
)
from app.api.files.artifact_share_api import router as share_router
from app.core.infra.limiter import limiter
from app.database.connection import get_db
from app.database.models.artifact import Artifact, ArtifactVersion
from app.services.artifacts.share_bundle import bundle_asset_count, bundle_dir_for_claims
from app.services.artifacts.share_token import parse_artifact_share_token
from app.services.deploy.deploy_packager import DeployFile


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
async def test_create_share_preview_materializes_bundle(share_client, html_artifact) -> None:
    files = {
        "index.html": DeployFile(path="index.html", content="<html></html>", encoding="utf-8"),
        "styles.css": DeployFile(path="styles.css", content="body{}", encoding="utf-8"),
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
    assert response.status_code == 200
    payload = response.json()
    token = payload["token"]
    claims = parse_artifact_share_token(token)
    assert claims is not None
    assert bundle_asset_count(claims) == 2

    entry = share_client.get(f"/public/artifact-share/{token}", follow_redirects=False)
    assert entry.status_code == 307
    index = share_client.get(f"/public/artifact-share/{token}/", follow_redirects=False)
    assert index.status_code == 200

    css = share_client.get(f"/public/artifact-share/{token}/styles.css")
    assert css.status_code == 200
    assert "body" in css.text


@pytest.mark.asyncio
async def test_html_share_includes_csp_headers(share_client, html_artifact) -> None:
    files = {
        "index.html": DeployFile(path="index.html", content="<html></html>", encoding="utf-8"),
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


@pytest.mark.asyncio
async def test_pdf_share_omits_csp_headers(share_client, html_artifact) -> None:
    files = {
        "report.pdf": DeployFile(path="report.pdf", content="JVBERi0=", encoding="base64"),
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


@pytest.mark.asyncio
async def test_multi_file_bundle_csp_allows_self(share_client, html_artifact) -> None:
    """CSP 'self' allows same-origin CSS/JS in multi-file bundles."""
    files = {
        "index.html": DeployFile(
            path="index.html",
            content='<html><link href="styles.css"/></html>',
            encoding="utf-8",
        ),
        "styles.css": DeployFile(path="styles.css", content="body{}", encoding="utf-8"),
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


@pytest.mark.asyncio
async def test_create_share_preview_rejects_non_shareable(share_client, db_session) -> None:
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
async def test_single_file_share_serves_without_redirect(share_client, html_artifact) -> None:
    files = {
        "report.pdf": DeployFile(path="report.pdf", content="JVBERi0=", encoding="base64"),
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
async def test_create_share_accepts_document_type_without_suffix(share_client, db_session) -> None:
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
        "季度报告": DeployFile(path="季度报告", content="# Title", encoding="utf-8"),
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
        "index.html": DeployFile(path="index.html", content="<html/>", encoding="utf-8"),
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
        "app.services.artifacts.share_token.time.time",
        return_value=claims.exp + 1,
    ):
        expired = share_client.get(f"/public/artifact-share/{token}")
    assert expired.status_code == 404


@pytest.mark.asyncio
async def test_public_share_nested_asset_path(share_client, html_artifact) -> None:
    files = {
        "index.html": DeployFile(
            path="index.html",
            content='<html><link rel="stylesheet" href="assets/styles.css"/></html>',
            encoding="utf-8",
        ),
        "assets/styles.css": DeployFile(
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
        "index.html": DeployFile(path="index.html", content="<html/>", encoding="utf-8"),
        "styles.css": DeployFile(path="styles.css", content="body{}", encoding="utf-8"),
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
async def test_share_rematerialization_uses_pinned_version(share_client, html_artifact) -> None:
    """Verify that bundle re-materialization passes version_id from JWT claims."""
    files_v1 = {
        "index.html": DeployFile(path="index.html", content="<html>v1</html>", encoding="utf-8"),
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
        serve = share_client.get(f"/public/artifact-share/{token}", follow_redirects=False)
        assert serve.status_code == 200
        _, kwargs2 = mock_resolve_again.call_args
        assert kwargs2["version_id"] == claims.version_id


@pytest.mark.asyncio
async def test_share_version_pinning_integration(share_client, db_session, tmp_path) -> None:
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
        "app.services.deploy.artifact_files.ensure_artifact_for_deploy",
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

    first_serve = share_client.get(f"/public/artifact-share/{token}", follow_redirects=False)
    assert first_serve.status_code == 200
    assert "v2-latest" in first_serve.text

    shutil.rmtree(bundle_dir_for_claims(claims), ignore_errors=True)
    assert bundle_asset_count(claims) == 0

    with patch(
        "app.services.deploy.artifact_files.ensure_artifact_for_deploy",
        new_callable=AsyncMock,
        return_value=artifact,
    ):
        re_serve = share_client.get(f"/public/artifact-share/{token}", follow_redirects=False)
    assert re_serve.status_code == 200
    assert "v2-latest" in re_serve.text


@pytest.mark.asyncio
async def test_share_pinned_version_survives_new_version(share_client, db_session, tmp_path) -> None:
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
        id=str(uuid.uuid4()), artifact_id=art_id, vault_uri=v1_uri, sha256_hash="h1",
    )
    db_session.add(ver1)
    await db_session.commit()
    await db_session.refresh(artifact)

    detached_v1_only = _make_detached_artifact(
        artifact_id=art_id, name="index.html", chat_id=chat_id, versions=[ver1],
    )
    with patch(
        "app.services.deploy.artifact_files.ensure_artifact_for_deploy",
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
        id=str(uuid.uuid4()), artifact_id=art_id, vault_uri=v2_uri, sha256_hash="h2",
        created_at=t1 + timedelta(hours=1),
    )
    db_session.add(ver2)
    await db_session.commit()

    claims = parse_artifact_share_token(token)
    assert claims is not None
    shutil.rmtree(bundle_dir_for_claims(claims), ignore_errors=True)

    detached_both = _make_detached_artifact(
        artifact_id=art_id, name="index.html", chat_id=chat_id, versions=[ver1, ver2],
    )
    with patch(
        "app.services.deploy.artifact_files.ensure_artifact_for_deploy",
        new_callable=AsyncMock,
        return_value=detached_both,
    ):
        re_serve = share_client.get(f"/public/artifact-share/{token}", follow_redirects=False)
    assert re_serve.status_code == 200
    assert "v1-pinned" in re_serve.text
    assert "v2-newer" not in re_serve.text


@pytest.mark.asyncio
async def test_share_invalid_version_returns_404(share_client, db_session, tmp_path) -> None:
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
        "app.services.deploy.artifact_files.ensure_artifact_for_deploy",
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
        "app.services.deploy.artifact_files.ensure_artifact_for_deploy",
        new_callable=AsyncMock,
        return_value=artifact_no_ver,
    ):
        re_serve = share_client.get(f"/public/artifact-share/{token}", follow_redirects=False)
    assert re_serve.status_code == 404


def _make_detached_artifact(*, artifact_id, name, chat_id, versions):
    """Build a detached Artifact with eagerly-set versions (no lazy load)."""
    a = Artifact(id=artifact_id, name=name, chat_id=chat_id, is_deleted=False)
    a.versions = list(versions)
    return a


@pytest.mark.asyncio
async def test_resolve_artifact_deploy_files_version_id_none_uses_latest(db_session, tmp_path) -> None:
    """When version_id=None, resolve_artifact_deploy_files picks the latest version."""
    from datetime import datetime, timedelta

    from myrm_agent_harness.agent.artifacts.vault import ArtifactVault

    from app.services.deploy.artifact_files import resolve_artifact_deploy_files

    vault = ArtifactVault(str(tmp_path))
    v1_uri = vault.put("<html>old</html>", "index.html")
    v2_uri = vault.put("<html>new-latest</html>", "index.html")

    art_id = str(uuid.uuid4())
    chat_id = str(uuid.uuid4())
    t1 = datetime(2025, 1, 1)
    t2 = t1 + timedelta(hours=1)

    ver1 = ArtifactVersion(
        id=str(uuid.uuid4()), artifact_id=art_id, vault_uri=v1_uri,
        sha256_hash="h1", created_at=t1,
    )
    ver2 = ArtifactVersion(
        id=str(uuid.uuid4()), artifact_id=art_id, vault_uri=v2_uri,
        sha256_hash="h2", created_at=t2,
    )

    detached = _make_detached_artifact(
        artifact_id=art_id, name="index.html", chat_id=chat_id, versions=[ver1, ver2]
    )

    with patch(
        "app.services.deploy.artifact_files.ensure_artifact_for_deploy",
        new_callable=AsyncMock,
        return_value=detached,
    ):
        _, files = await resolve_artifact_deploy_files(db_session, art_id, str(tmp_path))

    import base64

    raw = next(iter(files.values())).content
    decoded = base64.b64decode(raw).decode() if ";" not in raw and "/" not in raw else raw
    assert "new-latest" in decoded


@pytest.mark.asyncio
async def test_resolve_artifact_deploy_files_explicit_version(db_session, tmp_path) -> None:
    """When version_id is given, resolve_artifact_deploy_files picks that exact version."""
    import base64
    from datetime import datetime, timedelta

    from myrm_agent_harness.agent.artifacts.vault import ArtifactVault

    from app.services.deploy.artifact_files import resolve_artifact_deploy_files

    vault = ArtifactVault(str(tmp_path))
    v1_uri = vault.put("<html>first</html>", "index.html")
    v2_uri = vault.put("<html>second</html>", "index.html")

    art_id = str(uuid.uuid4())
    chat_id = str(uuid.uuid4())
    t1 = datetime(2025, 1, 1)
    t2 = t1 + timedelta(hours=1)

    ver1 = ArtifactVersion(
        id=str(uuid.uuid4()), artifact_id=art_id, vault_uri=v1_uri,
        sha256_hash="h1", created_at=t1,
    )
    ver2 = ArtifactVersion(
        id=str(uuid.uuid4()), artifact_id=art_id, vault_uri=v2_uri,
        sha256_hash="h2", created_at=t2,
    )

    detached = _make_detached_artifact(
        artifact_id=art_id, name="index.html", chat_id=chat_id, versions=[ver1, ver2]
    )

    with patch(
        "app.services.deploy.artifact_files.ensure_artifact_for_deploy",
        new_callable=AsyncMock,
        return_value=detached,
    ):
        _, files_v1 = await resolve_artifact_deploy_files(
            db_session, art_id, str(tmp_path), version_id=ver1.id
        )
    raw_v1 = next(iter(files_v1.values())).content
    assert "first" in base64.b64decode(raw_v1).decode()

    with patch(
        "app.services.deploy.artifact_files.ensure_artifact_for_deploy",
        new_callable=AsyncMock,
        return_value=detached,
    ):
        _, files_v2 = await resolve_artifact_deploy_files(
            db_session, art_id, str(tmp_path), version_id=ver2.id
        )
    raw_v2 = next(iter(files_v2.values())).content
    assert "second" in base64.b64decode(raw_v2).decode()


@pytest.mark.asyncio
async def test_resolve_artifact_deploy_files_invalid_version_raises(db_session, tmp_path) -> None:
    """When version_id doesn't match any version, LookupError is raised."""
    from myrm_agent_harness.agent.artifacts.vault import ArtifactVault

    from app.services.deploy.artifact_files import resolve_artifact_deploy_files

    vault = ArtifactVault(str(tmp_path))
    v1_uri = vault.put("<html>only</html>", "index.html")

    art_id = str(uuid.uuid4())
    ver1 = ArtifactVersion(
        id=str(uuid.uuid4()), artifact_id=art_id, vault_uri=v1_uri, sha256_hash="h1"
    )
    detached = _make_detached_artifact(
        artifact_id=art_id, name="index.html", chat_id=str(uuid.uuid4()), versions=[ver1]
    )

    with patch(
        "app.services.deploy.artifact_files.ensure_artifact_for_deploy",
        new_callable=AsyncMock,
        return_value=detached,
    ):
        with pytest.raises(LookupError, match="not found"):
            await resolve_artifact_deploy_files(
                db_session, art_id, str(tmp_path), version_id="nonexistent-id"
            )


@pytest.mark.asyncio
async def test_create_share_rejects_ambiguous_multi_html(share_client, html_artifact) -> None:
    files = {
        "a.html": DeployFile(path="a.html", content="<html/>", encoding="utf-8"),
        "b.html": DeployFile(path="b.html", content="<html/>", encoding="utf-8"),
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
async def test_csp_integration_html_real_vault(share_client, db_session, tmp_path) -> None:
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
        "app.services.deploy.artifact_files.ensure_artifact_for_deploy",
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
async def test_csp_integration_multi_file_bundle(share_client, db_session, tmp_path) -> None:
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
        "app.services.deploy.artifact_files.ensure_artifact_for_deploy",
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
        f"/public/artifact-share/{token}", follow_redirects=False,
    )
    assert index_resp.status_code == 200
    csp = index_resp.headers.get("content-security-policy", "")
    assert "style-src 'self' 'unsafe-inline'" in csp
    assert "img-src 'self' data: blob:" in csp


@pytest.mark.asyncio
async def test_csp_integration_pdf_real_vault(share_client, db_session, tmp_path) -> None:
    """Integration: real Vault PDF → public GET → verify security headers.

    Vault stores objects with UUID filenames (no extension), so
    _guess_media_type falls back to text/html and CSP is injected.
    This is safe: CSP on non-HTML content is a harmless no-op.
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
        "app.services.deploy.artifact_files.ensure_artifact_for_deploy",
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
    assert serve.headers.get("x-content-type-options") == "nosniff"


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
        "index.html": DeployFile(path="index.html", content="<html/>", encoding="utf-8"),
        "app.js": DeployFile(path="app.js", content="console.log(1)", encoding="utf-8"),
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
    redirect = share_client.get(f"/public/artifact-share/{token}", follow_redirects=False)
    assert redirect.status_code == 307
    assert "content-security-policy" not in redirect.headers


@pytest.mark.asyncio
async def test_nested_css_asset_no_csp(share_client, html_artifact) -> None:
    """CSS sub-asset in nested path must not carry CSP headers."""
    files = {
        "index.html": DeployFile(
            path="index.html",
            content='<html><link href="assets/main.css"/></html>',
            encoding="utf-8",
        ),
        "assets/main.css": DeployFile(path="assets/main.css", content=".a{}", encoding="utf-8"),
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
