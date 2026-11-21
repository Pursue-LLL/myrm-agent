"""Share creation through the preview API: success, validation and the error mapping of the creation pipeline."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.database.models.artifact import Artifact, ArtifactVersion
from app.services.artifacts.share.share_bundle import (
    bundle_asset_count,
)
from app.services.artifacts.share.share_token import (
    parse_artifact_share_token,
)
from app.services.hosting.packager import PublishFile

pytestmark = pytest.mark.usefixtures("chats_share_workspace")


@pytest.mark.asyncio
async def test_create_share_preview_materializes_bundle(share_client, html_artifact) -> None:
    files = {
        "index.html": PublishFile(path="index.html", content="<html></html>", encoding="utf-8"),
        "styles.css": PublishFile(path="styles.css", content="body{}", encoding="utf-8"),
    }
    with (
        patch(
            "app.services.artifacts.share.share_bundle.resolve_artifact_deploy_files",
            new_callable=AsyncMock,
            return_value=(html_artifact, files),
        ),
        patch(
            "app.core.infra.ingress.get_public_ingress_base_url",
            new_callable=AsyncMock,
            return_value="",
        ),
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
async def test_create_share_preview_exposes_absolute_share_url(share_client, html_artifact) -> None:
    """Create response carries an absolute share_url when public ingress is set."""
    files = {
        "index.html": PublishFile(path="index.html", content="<html></html>", encoding="utf-8"),
    }
    with (
        patch(
            "app.services.artifacts.share.share_bundle.resolve_artifact_deploy_files",
            new_callable=AsyncMock,
            return_value=(html_artifact, files),
        ),
        patch(
            "app.core.infra.ingress.get_public_ingress_base_url",
            new_callable=AsyncMock,
            return_value="https://myrm-x.example.com",
        ),
    ):
        response = share_client.post(
            f"/{html_artifact.id}/share-preview",
            json={"ttl_days": 7, "artifact_type": "html"},
        )
    assert response.status_code == 200
    payload = response.json()
    assert payload["share_url"] == (f"https://myrm-x.example.com{payload['share_path']}")


@pytest.mark.asyncio
async def test_create_share_preview_share_url_falls_back_when_ingress_fails(share_client, html_artifact) -> None:
    """Ingress resolution failure must not fail share creation (degrade to None)."""
    files = {
        "index.html": PublishFile(path="index.html", content="<html></html>", encoding="utf-8"),
    }
    with (
        patch(
            "app.services.artifacts.share.share_bundle.resolve_artifact_deploy_files",
            new_callable=AsyncMock,
            return_value=(html_artifact, files),
        ),
        patch(
            "app.core.infra.ingress.get_public_ingress_base_url",
            new_callable=AsyncMock,
            side_effect=RuntimeError("ingress unavailable"),
        ),
    ):
        response = share_client.post(
            f"/{html_artifact.id}/share-preview",
            json={"ttl_days": 7, "artifact_type": "html"},
        )
    assert response.status_code == 200
    payload = response.json()
    assert payload["share_url"] is None


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
        "季度报告": PublishFile(path="季度报告", content="# Title", encoding="utf-8"),
    }
    with patch(
        "app.services.artifacts.share.share_bundle.resolve_artifact_deploy_files",
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
        "app.services.artifacts.share.share_bundle.resolve_artifact_deploy_files",
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
async def test_create_share_rejects_ambiguous_multi_html(share_client, html_artifact) -> None:
    files = {
        "a.html": PublishFile(path="a.html", content="<html/>", encoding="utf-8"),
        "b.html": PublishFile(path="b.html", content="<html/>", encoding="utf-8"),
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
    assert response.status_code == 400


@pytest.mark.parametrize(
    ("exc", "status"),
    [
        (ValueError("boom"), 400),
        (LookupError("gone"), 404),
        (FileNotFoundError("gone"), 404),
    ],
)
@pytest.mark.asyncio
async def test_create_share_materialize_error_mapping(share_client, html_artifact, exc: Exception, status: int) -> None:
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
