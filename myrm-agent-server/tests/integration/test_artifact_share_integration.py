"""Real artifact share integration: vault object -> bundle -> public HTTP access.

Covers the full public share chain without mocking vault collection:
``ArtifactVault.put`` -> DB artifact/version -> create share (real
materialization) -> public entry redirect -> static asset serving, plus the
password gate flow with signed unlock cookie.
"""

from __future__ import annotations

import re
import shutil
import uuid
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from myrm_agent_harness.agent.artifacts.vault import ArtifactVault
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.dependencies import get_workspace_root
from app.api.files.artifact_share_api import router as share_router
from app.api.files.artifact_share_public import public_router
from app.core.infra.limiter import limiter
from app.core.security.share_unlock import unlock_cookie_name
from app.database.connection import get_db
from app.database.models import Base
from app.database.models.artifact import Artifact, ArtifactVersion
from app.services.artifacts.share_bundle import (
    bundle_asset_count,
    bundle_dir_for_claims,
)
from app.services.artifacts.share_token import parse_artifact_share_token


@pytest.fixture
async def db_session():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session
    await engine.dispose()


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


async def _seed_html_artifact(
    db_session: AsyncSession,
    workspace_root: Path,
    *,
    html: str,
    sandbox_assets: dict[str, str] | None = None,
    password: str | None = None,
    name: str = "index.html",
) -> tuple[Artifact, str]:
    """Insert a real vault-backed artifact (optionally mirrored in sandbox).

    ``name`` becomes both the artifact name and the vault object filename; pass
    an extension-less name to exercise document-type shares.
    """
    vault = ArtifactVault(str(workspace_root))
    vault_uri = vault.put(html, name, content_type="text/html")

    chat_id = str(uuid.uuid4())
    if sandbox_assets:
        sandbox_dir = workspace_root / "sandboxes" / chat_id
        sandbox_dir.mkdir(parents=True, exist_ok=True)
        for asset_name, content in sandbox_assets.items():
            asset_path = sandbox_dir / asset_name
            asset_path.parent.mkdir(parents=True, exist_ok=True)
            asset_path.write_text(content, encoding="utf-8")

    artifact = Artifact(
        id=str(uuid.uuid4()),
        name=name,
        chat_id=chat_id,
        is_deleted=False,
    )
    db_session.add(artifact)
    await db_session.flush()
    version = ArtifactVersion(
        id=str(uuid.uuid4()),
        artifact_id=artifact.id,
        vault_uri=vault_uri,
        sha256_hash="unused-hash",
    )
    db_session.add(version)
    await db_session.commit()
    await db_session.refresh(artifact)
    return artifact, vault_uri


def _extract_unlock_cookie(response: TestClient.response_class) -> str | None:
    match = re.search(r"artifact_share_unlock_[a-f0-9]+=([^;]+)", response.headers.get("set-cookie", ""))
    return match.group(1) if match else None


HTML_WITH_CSS = (
    '<!doctype html><html><head><link rel="stylesheet" href="styles.css"></head>'
    "<body><h1>Share me</h1></body></html>"
)


@pytest.mark.asyncio
async def test_single_file_html_share_real_vault(share_client, db_session, tmp_path) -> None:
    """Single-file share serves the vault object directly with security headers."""
    artifact, _ = await _seed_html_artifact(db_session, tmp_path, html=HTML_WITH_CSS)

    response = share_client.post(
        f"/{artifact.id}/share-preview",
        json={"ttl_days": 7, "artifact_type": "html"},
    )
    assert response.status_code == 200
    token = response.json()["token"]
    claims = parse_artifact_share_token(token)
    assert claims is not None
    assert bundle_asset_count(claims) == 1

    index = share_client.get(f"/public/artifact-share/{token}", follow_redirects=False)
    assert index.status_code == 200
    assert "Share me" in index.text
    assert "default-src 'none'" in index.headers["content-security-policy"]
    assert index.headers["x-content-type-options"] == "nosniff"
    assert index.headers["x-frame-options"] == "DENY"


@pytest.mark.asyncio
async def test_multi_file_share_real_vault_and_sandbox(share_client, db_session, tmp_path) -> None:
    """Multi-file bundle redirects to a trailing slash and serves sandbox assets."""
    artifact, _ = await _seed_html_artifact(
        db_session,
        tmp_path,
        html=HTML_WITH_CSS,
        sandbox_assets={
            "index.html": HTML_WITH_CSS,
            "styles.css": "body{color:#222}",
        },
    )

    response = share_client.post(
        f"/{artifact.id}/share-preview",
        json={"ttl_days": 7, "artifact_type": "html"},
    )
    assert response.status_code == 200
    token = response.json()["token"]
    claims = parse_artifact_share_token(token)
    assert claims is not None
    # Real collection: vault object is stored as an extension-less UUID file;
    # collect_publish_files now names it from artifact.name, so the bundle
    # holds exactly the sandbox mirror pair (index.html + styles.css).
    assert bundle_asset_count(claims) == 2

    entry = share_client.get(f"/public/artifact-share/{token}", follow_redirects=False)
    assert entry.status_code == 307
    assert entry.headers["location"].endswith(f"/public/artifact-share/{token}/")

    index = share_client.get(f"/public/artifact-share/{token}/", follow_redirects=False)
    assert index.status_code == 200
    assert "Share me" in index.text

    css = share_client.get(f"/public/artifact-share/{token}/styles.css")
    assert css.status_code == 200
    assert "color:#222" in css.text


@pytest.mark.asyncio
async def test_password_share_full_flow_real_vault(share_client, db_session, tmp_path) -> None:
    """Password share gate + signed unlock cookie authorize real asset requests."""
    artifact, _ = await _seed_html_artifact(
        db_session,
        tmp_path,
        html=HTML_WITH_CSS,
        sandbox_assets={
            "index.html": HTML_WITH_CSS,
            "styles.css": "body{color:#333}",
        },
        password="s3cret",
    )

    response = share_client.post(
        f"/{artifact.id}/share-preview",
        json={"ttl_days": 7, "artifact_type": "html", "password": "s3cret"},
    )
    assert response.status_code == 200
    token = response.json()["token"]

    gated = share_client.get(f"/public/artifact-share/{token}", follow_redirects=False)
    assert gated.status_code == 403

    unlocked = share_client.get(
        f"/public/artifact-share/{token}?p=s3cret", follow_redirects=False
    )
    assert unlocked.status_code == 307
    index = share_client.get(
        f"/public/artifact-share/{token}/?p=s3cret", follow_redirects=False
    )
    assert index.status_code == 200
    unlock = _extract_unlock_cookie(index)
    assert unlock is not None

    css = share_client.get(
        f"/public/artifact-share/{token}/styles.css",
        headers={"Cookie": f"{unlock_cookie_name('artifact_share_unlock', token)}={unlock}"},
    )
    assert css.status_code == 200
    assert "color:#333" in css.text

    gated_asset = share_client.get(f"/public/artifact-share/{token}/styles.css")
    assert gated_asset.status_code == 403

    wrong = share_client.get(
        f"/public/artifact-share/{token}/?p=wrong", follow_redirects=False
    )
    assert wrong.status_code == 403


@pytest.mark.asyncio
async def test_pdf_share_real_vault_serves_pdf_media_type(
    share_client, db_session, tmp_path
) -> None:
    """Extension-less vault PDF object must be served as application/pdf.

    Regression for the physical-uuid naming bug: without the artifact-name hint
    the bundle entry was the opaque UUID, so ``_guess_media_type`` fell back to
    text/html and served corrupted PDF bytes.
    """
    vault = ArtifactVault(str(tmp_path))
    pdf_bytes = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF"
    vault_uri = vault.put(pdf_bytes, "report.pdf", content_type="application/pdf")

    artifact = Artifact(
        id=str(uuid.uuid4()),
        name="report.pdf",
        chat_id=str(uuid.uuid4()),
        is_deleted=False,
    )
    db_session.add(artifact)
    await db_session.flush()
    db_session.add(
        ArtifactVersion(
            id=str(uuid.uuid4()),
            artifact_id=artifact.id,
            vault_uri=vault_uri,
            sha256_hash="unused-hash",
        )
    )
    await db_session.commit()
    await db_session.refresh(artifact)

    response = share_client.post(
        f"/{artifact.id}/share-preview",
        json={"ttl_days": 7, "artifact_type": "pdf"},
    )
    assert response.status_code == 200
    token = response.json()["token"]

    entry = share_client.get(f"/public/artifact-share/{token}", follow_redirects=False)
    assert entry.status_code == 200
    assert entry.headers["content-type"].startswith("application/pdf")
    assert entry.content.startswith(b"%PDF")


@pytest.mark.asyncio
async def test_bundle_removed_then_re_materialized(
    share_client, db_session, tmp_path
) -> None:
    """Deleting the materialized bundle self-heals on the next public access."""
    artifact, _ = await _seed_html_artifact(
        db_session, tmp_path, html="<h1>self-heal</h1>"
    )
    response = share_client.post(
        f"/{artifact.id}/share-preview",
        json={"ttl_days": 7, "artifact_type": "html"},
    )
    assert response.status_code == 200
    token = response.json()["token"]
    claims = parse_artifact_share_token(token)
    assert claims is not None
    bundle_dir = bundle_dir_for_claims(claims)
    assert bundle_dir.is_dir()

    shutil.rmtree(bundle_dir)
    assert not bundle_dir.exists()

    index = share_client.get(f"/public/artifact-share/{token}", follow_redirects=False)
    assert index.status_code == 200
    assert "self-heal" in index.text
    assert bundle_dir.is_dir()


@pytest.mark.asyncio
async def test_invalid_manifest_and_traversal_rejected(
    share_client, db_session, tmp_path
) -> None:
    """Invalid token, manifest.json, and traversal attempts all return 404."""
    artifact, _ = await _seed_html_artifact(
        db_session,
        tmp_path,
        html=HTML_WITH_CSS,
        sandbox_assets={
            "index.html": HTML_WITH_CSS,
            "styles.css": "body{}",
        },
    )
    response = share_client.post(
        f"/{artifact.id}/share-preview",
        json={"ttl_days": 7, "artifact_type": "html"},
    )
    token = response.json()["token"]

    assert share_client.get("/public/artifact-share/not-a-token").status_code == 404
    assert (
        share_client.get(
            f"/public/artifact-share/{token}/manifest.json",
        ).status_code
        == 404
    )
    assert (
        share_client.get(
            f"/public/artifact-share/{token}/../manifest.json",
        ).status_code
        == 404
    )
    assert (
        share_client.get(
            f"/public/artifact-share/{token}/%2e%2e/manifest.json",
        ).status_code
        == 404
    )


@pytest.mark.asyncio
async def test_nested_asset_and_binary_real_vault(
    share_client, db_session, tmp_path
) -> None:
    """Deeply nested resources and binary assets are served from the bundle."""
    html = (
        '<!doctype html><html><body><img src="assets/img/logo.png"></body></html>'
    )
    artifact, _ = await _seed_html_artifact(
        db_session,
        tmp_path,
        html=html,
        sandbox_assets={
            "index.html": html,
            "assets/img/logo.png": "logo-placeholder",
        },
    )
    response = share_client.post(
        f"/{artifact.id}/share-preview",
        json={"ttl_days": 7, "artifact_type": "html"},
    )
    assert response.status_code == 200
    token = response.json()["token"]
    claims = parse_artifact_share_token(token)
    assert claims is not None
    assert bundle_asset_count(claims) == 2

    logo = share_client.get(f"/public/artifact-share/{token}/assets/img/logo.png")
    assert logo.status_code == 200
    assert logo.content == b"logo-placeholder"


@pytest.mark.asyncio
async def test_document_share_without_suffix_real_vault(
    share_client, db_session, tmp_path
) -> None:
    """Extension-less document artifacts share via the SSE artifact_type hint."""
    markdown = "# 季度报告\n\n已完成全部交付物。"
    artifact, _ = await _seed_html_artifact(
        db_session, tmp_path, html=markdown, name="季度报告"
    )
    response = share_client.post(
        f"/{artifact.id}/share-preview",
        json={"ttl_days": 7, "artifact_type": "document"},
    )
    assert response.status_code == 200
    token = response.json()["token"]

    entry = share_client.get(f"/public/artifact-share/{token}", follow_redirects=False)
    assert entry.status_code == 200
    assert "季度报告" in entry.text
    # Extension-less document entries resolve their media type from the share
    # token's artifact_type instead of the text/html fallback.
    assert entry.headers["content-type"].startswith("text/markdown")

