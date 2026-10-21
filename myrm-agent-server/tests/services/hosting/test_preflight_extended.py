"""Extended preflight tests including run_deploy_preflight."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.artifact import Artifact, ArtifactVersion
from app.services.hosting.packager import PublishFile
from app.services.hosting.preflight import evaluate_deploy_preflight, run_deploy_preflight


def test_evaluate_deploy_preflight_empty_payload() -> None:
    result = evaluate_deploy_preflight({})
    assert result.deployable is False
    assert result.reason == "EMPTY_PAYLOAD"


def test_evaluate_deploy_preflight_requires_html_entry() -> None:
    result = evaluate_deploy_preflight({"style.css": PublishFile(path="style.css", content="body{}")})
    assert result.deployable is False
    assert result.reason == "REQUIRES_HTML_ENTRY"


@pytest.mark.asyncio
async def test_run_deploy_preflight_artifact_not_found(db_session: AsyncSession) -> None:
    with patch(
        "app.services.hosting.preflight.resolve_artifact_deploy_files",
        new_callable=AsyncMock,
        side_effect=LookupError("missing"),
    ):
        result = await run_deploy_preflight(db_session, "missing-artifact", "/tmp")
    assert result.reason == "PACKAGING_ERROR"


@pytest.mark.asyncio
async def test_run_deploy_preflight_no_versions_in_db(db_session: AsyncSession) -> None:
    artifact_id = str(uuid.uuid4())
    artifact = Artifact(id=artifact_id, name="empty.html", is_deleted=False)
    db_session.add(artifact)
    await db_session.commit()

    result = await run_deploy_preflight(db_session, artifact_id, "/tmp")
    assert result.reason == "NO_VERSIONS"


@pytest.mark.asyncio
async def test_run_deploy_preflight_ok(db_session: AsyncSession) -> None:
    artifact_id = str(uuid.uuid4())
    artifact = Artifact(id=artifact_id, name="index.html", is_deleted=False)
    version = ArtifactVersion(
        id=str(uuid.uuid4()),
        artifact_id=artifact_id,
        vault_uri="vault://x",
        sha256_hash="hash",
        created_at=datetime.now(UTC),
    )
    artifact.versions = [version]
    db_session.add(artifact)
    db_session.add(version)
    await db_session.commit()

    files = {"index.html": PublishFile(path="index.html", content="<html/>")}
    with patch(
        "app.services.hosting.preflight.resolve_artifact_deploy_files",
        new_callable=AsyncMock,
        return_value=(artifact, files),
    ):
        result = await run_deploy_preflight(db_session, artifact_id, "/tmp")

    assert result.deployable is True
    assert result.reason == "OK"


@pytest.mark.asyncio
async def test_run_deploy_preflight_file_not_found(db_session: AsyncSession) -> None:
    with patch(
        "app.services.hosting.preflight.resolve_artifact_deploy_files",
        new_callable=AsyncMock,
        side_effect=FileNotFoundError("missing on disk"),
    ):
        result = await run_deploy_preflight(db_session, "art-1", "/tmp")
    assert result.reason == "PACKAGING_ERROR"
    assert "missing on disk" in result.message


@pytest.mark.asyncio
async def test_run_deploy_preflight_generic_exception(db_session: AsyncSession) -> None:
    with patch(
        "app.services.hosting.preflight.resolve_artifact_deploy_files",
        new_callable=AsyncMock,
        side_effect=RuntimeError("boom"),
    ):
        result = await run_deploy_preflight(db_session, "art-1", "/tmp")
    assert result.reason == "PACKAGING_ERROR"
    assert "Failed to read artifact files" in result.message


@pytest.mark.asyncio
async def test_run_deploy_preflight_value_error_other(db_session: AsyncSession) -> None:
    with patch(
        "app.services.hosting.preflight.resolve_artifact_deploy_files",
        new_callable=AsyncMock,
        side_effect=ValueError("bad payload"),
    ):
        result = await run_deploy_preflight(db_session, "art-1", "/tmp")
    assert result.reason == "PACKAGING_ERROR"
    assert result.message == "bad payload"
