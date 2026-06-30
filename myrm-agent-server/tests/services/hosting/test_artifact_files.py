"""Tests for artifact deploy file resolution."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.artifact import Artifact, ArtifactVersion
from app.services.hosting.artifact_files import resolve_artifact_deploy_files
from app.services.hosting.packager import PublishFile


@pytest.mark.asyncio
async def test_resolve_artifact_deploy_files_latest_version(tmp_path: Path, db_session: AsyncSession) -> None:
    artifact_id = str(uuid.uuid4())
    version_id = str(uuid.uuid4())
    artifact = Artifact(id=artifact_id, name="index.html", chat_id=None)
    version = ArtifactVersion(
        id=version_id,
        artifact_id=artifact_id,
        vault_uri="vault://obj-1",
        sha256_hash="abc",
        created_at=datetime.now(UTC),
    )
    artifact.versions = [version]
    db_session.add(artifact)
    db_session.add(version)
    await db_session.commit()

    html_path = tmp_path / "obj-1"
    html_path.write_text("<html><body>Hi</body></html>", encoding="utf-8")
    files_map = {"index.html": PublishFile(path="index.html", content="<html><body>Hi</body></html>")}

    with patch(
        "app.services.hosting.artifact_files.ensure_artifact_for_deploy",
        new_callable=AsyncMock,
        return_value=artifact,
    ):
        with patch("app.services.hosting.artifact_files.ArtifactVault") as mock_vault_cls:
            mock_vault = MagicMock()
            mock_vault.get_object_path.return_value = html_path
            mock_vault_cls.return_value = mock_vault
            with patch(
                "app.services.hosting.artifact_files.collect_publish_files",
                return_value=files_map,
            ):
                loaded, files = await resolve_artifact_deploy_files(db_session, artifact_id, str(tmp_path))

    assert loaded.id == artifact_id
    assert "index.html" in files


@pytest.mark.asyncio
async def test_resolve_artifact_deploy_files_no_versions(db_session: AsyncSession) -> None:
    artifact = Artifact(id=str(uuid.uuid4()), name="empty.html")
    artifact.versions = []

    with patch(
        "app.services.hosting.artifact_files.ensure_artifact_for_deploy",
        new_callable=AsyncMock,
        return_value=artifact,
    ):
        with pytest.raises(ValueError, match="NO_VERSIONS"):
            await resolve_artifact_deploy_files(db_session, artifact.id, "/tmp")


@pytest.mark.asyncio
async def test_resolve_artifact_deploy_files_specific_version_not_found(db_session: AsyncSession) -> None:
    artifact_id = str(uuid.uuid4())
    artifact = Artifact(id=artifact_id, name="page.html")
    version = ArtifactVersion(
        id=str(uuid.uuid4()),
        artifact_id=artifact_id,
        vault_uri="vault://obj",
        sha256_hash="abc",
        created_at=datetime.now(UTC),
    )
    artifact.versions = [version]

    with patch(
        "app.services.hosting.artifact_files.ensure_artifact_for_deploy",
        new_callable=AsyncMock,
        return_value=artifact,
    ):
        with pytest.raises(LookupError, match="version"):
            await resolve_artifact_deploy_files(db_session, artifact_id, "/tmp", version_id="missing-version")


@pytest.mark.asyncio
async def test_resolve_artifact_deploy_files_with_asset_root(tmp_path: Path, db_session: AsyncSession) -> None:
    artifact_id = str(uuid.uuid4())
    artifact = Artifact(id=artifact_id, name="index.html", chat_id="chat-1")
    version = ArtifactVersion(
        id=str(uuid.uuid4()),
        artifact_id=artifact_id,
        vault_uri="vault://obj-2",
        sha256_hash="abc",
        created_at=datetime.now(UTC),
    )
    artifact.versions = [version]
    html_path = tmp_path / "obj-2"
    html_path.write_text("<html/>", encoding="utf-8")
    sandbox_html = tmp_path / "sandbox" / "index.html"
    sandbox_html.parent.mkdir(parents=True)
    sandbox_html.write_text("<html/>", encoding="utf-8")
    files_map = {"index.html": PublishFile(path="index.html", content="<html/>")}

    with patch(
        "app.services.hosting.artifact_files.ensure_artifact_for_deploy",
        new_callable=AsyncMock,
        return_value=artifact,
    ):
        with patch("app.services.hosting.artifact_files.ArtifactVault") as mock_vault_cls:
            mock_vault = MagicMock()
            mock_vault.get_object_path.return_value = html_path
            mock_vault_cls.return_value = mock_vault
            with patch(
                "app.services.hosting.artifact_files.resolve_sandbox_file_path",
                return_value=str(sandbox_html),
            ):
                with patch(
                    "app.services.hosting.artifact_files.collect_publish_files",
                    return_value=files_map,
                ) as mock_collect:
                    await resolve_artifact_deploy_files(db_session, artifact_id, str(tmp_path))

    mock_collect.assert_called_once()
    assert mock_collect.call_args.kwargs["asset_root"] == sandbox_html.parent
