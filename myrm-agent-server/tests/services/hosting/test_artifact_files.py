"""Tests for artifact deploy file resolution."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.artifacts.listener import upsert_processor_artifact
from app.core.artifacts.source_path import to_source_path
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


_PAGE = '<link rel="stylesheet" href="style.css"><h1>page</h1>'


def _site(directory: Path, color: str) -> Path:
    """An index page whose stylesheet sits next to it."""
    directory.mkdir(parents=True)
    (directory / "style.css").write_text(f"body {{ color: {color}; }}", encoding="utf-8")
    page = directory / "index.html"
    page.write_text(_PAGE, encoding="utf-8")
    return page


async def _register(db_session: AsyncSession, workspace: Path, page: Path, *, record_path: bool = True) -> str:
    artifact_id = f"file_{uuid.uuid4().hex[:12]}"
    await upsert_processor_artifact(
        db_session,
        file_id=artifact_id,
        filename=page.name,
        sandbox_path=str(page),
        workspace_root=str(workspace),
        chat_id="chat-1",
        source_path=to_source_path(str(page), str(workspace)) if record_path else None,
    )
    return artifact_id


async def _deploy_files(db_session: AsyncSession, workspace: Path, artifact_id: str) -> dict[str, PublishFile]:
    with patch(
        "app.services.hosting.artifact_files.resolve_chat_workspace_root",
        new_callable=AsyncMock,
        return_value=workspace,
    ):
        _, files = await resolve_artifact_deploy_files(db_session, artifact_id, str(workspace))
    return files


@pytest.mark.asyncio
async def test_same_named_pages_in_two_folders_each_ship_their_own_files(tmp_path: Path, db_session: AsyncSession) -> None:
    workspace = tmp_path / "ws"
    page_a = _site(workspace / "site-a", "red")
    page_b = _site(workspace / "site-b", "blue")
    id_a = await _register(db_session, workspace, page_a)
    id_b = await _register(db_session, workspace, page_b)

    files_a = await _deploy_files(db_session, workspace, id_a)
    files_b = await _deploy_files(db_session, workspace, id_b)

    assert files_a["style.css"].content == "body { color: red; }"
    assert files_b["style.css"].content == "body { color: blue; }"


@pytest.mark.asyncio
async def test_a_file_outside_the_workspace_ships_the_files_next_to_it(tmp_path: Path, db_session: AsyncSession) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    page = _site(tmp_path / "elsewhere", "green")
    artifact_id = await _register(db_session, workspace, page)

    files = await _deploy_files(db_session, workspace, artifact_id)

    assert files["style.css"].content == "body { color: green; }"


@pytest.mark.asyncio
async def test_a_deleted_source_file_publishes_the_stored_version_without_searching_by_name(
    tmp_path: Path, db_session: AsyncSession
) -> None:
    workspace = tmp_path / "ws"
    page = _site(workspace / "site-a", "red")
    other = _site(workspace / "site-b", "blue")
    artifact_id = await _register(db_session, workspace, page)
    page.unlink()
    assert other.is_file()

    with patch("app.services.hosting.artifact_files.resolve_sandbox_file_path") as by_name:
        files = await _deploy_files(db_session, workspace, artifact_id)

    by_name.assert_not_called()
    assert "style.css" not in files
    assert files["index.html"].content == _PAGE


@pytest.mark.asyncio
async def test_a_row_without_a_source_path_is_found_by_name_and_logged(
    tmp_path: Path, db_session: AsyncSession, caplog: pytest.LogCaptureFixture
) -> None:
    workspace = tmp_path / "ws"
    page = _site(workspace / "site-a", "red")
    artifact_id = await _register(db_session, workspace, page, record_path=False)

    with caplog.at_level(logging.WARNING, logger="app.services.hosting.artifact_files"):
        files = await _deploy_files(db_session, workspace, artifact_id)

    assert files["style.css"].content == "body { color: red; }"
    assert [record.getMessage() for record in caplog.records if artifact_id in record.getMessage()] == [
        f"Artifact {artifact_id} has no source path; locating its files by the name 'index.html'"
    ]
