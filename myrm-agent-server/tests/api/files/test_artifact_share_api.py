"""API tests for artifact share preview and public bundle routes."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.dependencies import get_workspace_root
from app.api.files.artifact_share_api import public_router, router as share_router
from app.core.infra.limiter import limiter
from app.database.connection import get_db
from app.database.models.artifact import Artifact, ArtifactVersion
from app.services.artifacts.share_bundle import bundle_asset_count
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
