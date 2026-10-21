"""Unit tests for publish orchestrator."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.artifact import Artifact, ArtifactVersion
from app.services.hosting.orchestrator import publish_artifact_to_target
from app.services.hosting.packager import PublishFile
from app.services.hosting.preflight import DeployPreflightResult
from app.services.hosting.targets import LEGACY_VERCEL_TARGET_ID, save_hosting_targets
from app.services.hosting.types import HostingTarget, PublicationResult


@pytest.mark.asyncio
async def test_publish_target_not_found(db_session: AsyncSession) -> None:
    result = await publish_artifact_to_target(
        db_session,
        "missing-artifact",
        "/tmp/workspace",
        hosting_target_id="missing-target",
    )
    assert result.success is False
    assert result.error == "Hosting target not found."


@pytest.mark.asyncio
async def test_publish_artifact_not_found(db_session: AsyncSession) -> None:
    await save_hosting_targets(
        db_session,
        [HostingTarget(id=LEGACY_VERCEL_TARGET_ID, name="Vercel", provider_type="vercel", config={}, is_default=True)],
    )
    with patch(
        "app.services.hosting.orchestrator.resolve_artifact_deploy_files",
        new_callable=AsyncMock,
        side_effect=LookupError("Artifact not found"),
    ):
        result = await publish_artifact_to_target(
            db_session,
            "missing-artifact",
            "/tmp/workspace",
            hosting_target_id=LEGACY_VERCEL_TARGET_ID,
        )
    assert result.success is False
    assert result.error == "Artifact not found."


@pytest.mark.asyncio
async def test_publish_preflight_failed(db_session: AsyncSession) -> None:
    await save_hosting_targets(
        db_session,
        [HostingTarget(id=LEGACY_VERCEL_TARGET_ID, name="Vercel", provider_type="vercel", config={}, is_default=True)],
    )
    artifact = Artifact(id=str(uuid.uuid4()), name="app.tsx")
    version = ArtifactVersion(
        id=str(uuid.uuid4()),
        artifact_id=artifact.id,
        vault_uri="vault://x",
        sha256_hash="hash",
        created_at=datetime.now(UTC),
    )
    artifact.versions = [version]
    files = {"App.tsx": PublishFile(path="App.tsx", content="export default 1")}

    with patch(
        "app.services.hosting.orchestrator.resolve_artifact_deploy_files",
        new_callable=AsyncMock,
        return_value=(artifact, files),
    ):
        with patch(
            "app.services.hosting.orchestrator.evaluate_deploy_preflight",
            return_value=DeployPreflightResult(
                deployable=False,
                reason="CODE_REQUIRES_HTML_ARTIFACT",
                message="Need HTML",
                hint=None,
            ),
        ):
            result = await publish_artifact_to_target(
                db_session,
                artifact.id,
                "/tmp/workspace",
                hosting_target_id=LEGACY_VERCEL_TARGET_ID,
            )
    assert result.success is False
    assert result.status == "PREFLIGHT_FAILED"


@pytest.mark.asyncio
async def test_publish_success_persists_publication_row(db_session: AsyncSession) -> None:
    await save_hosting_targets(
        db_session,
        [HostingTarget(id=LEGACY_VERCEL_TARGET_ID, name="Vercel", provider_type="vercel", config={}, is_default=True)],
    )
    artifact_id = str(uuid.uuid4())
    version_id = str(uuid.uuid4())
    artifact = Artifact(id=artifact_id, name="index.html")
    version = ArtifactVersion(
        id=version_id,
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
    mock_provider = MagicMock()
    mock_provider.publish = AsyncMock(
        return_value=PublicationResult(
            success=True,
            url="https://ok.vercel.app",
            publication_id="dep_ok",
            project_ref="prj_ok",
            status="READY",
        )
    )

    with patch(
        "app.services.hosting.orchestrator.resolve_artifact_deploy_files",
        new_callable=AsyncMock,
        return_value=(artifact, files),
    ):
        with patch(
            "app.services.hosting.orchestrator.resolve_target_credentials",
            new_callable=AsyncMock,
            return_value={"token": "tok"},
        ):
            with patch("app.services.hosting.orchestrator.get_hosting_provider", return_value=mock_provider):
                result = await publish_artifact_to_target(
                    db_session,
                    artifact_id,
                    "/tmp/workspace",
                    hosting_target_id=LEGACY_VERCEL_TARGET_ID,
                )

    assert result.success is True
    assert result.publication_row_id
    assert result.publication_id == "dep_ok"
    assert result.latest_version_id == version_id


@pytest.mark.asyncio
async def test_publish_no_versions(db_session: AsyncSession) -> None:
    await save_hosting_targets(
        db_session,
        [HostingTarget(id=LEGACY_VERCEL_TARGET_ID, name="Vercel", provider_type="vercel", config={}, is_default=True)],
    )
    artifact = Artifact(id=str(uuid.uuid4()), name="index.html")
    artifact.versions = []

    with patch(
        "app.services.hosting.orchestrator.resolve_artifact_deploy_files",
        new_callable=AsyncMock,
        side_effect=ValueError("NO_VERSIONS"),
    ):
        result = await publish_artifact_to_target(
            db_session,
            artifact.id,
            "/tmp/workspace",
            hosting_target_id=LEGACY_VERCEL_TARGET_ID,
        )
    assert result.status == "PREFLIGHT_FAILED"
    assert "no versions" in result.error.lower()


@pytest.mark.asyncio
async def test_publish_credentials_missing(db_session: AsyncSession) -> None:
    await save_hosting_targets(
        db_session,
        [HostingTarget(id=LEGACY_VERCEL_TARGET_ID, name="Vercel", provider_type="vercel", config={}, is_default=True)],
    )
    artifact_id = str(uuid.uuid4())
    artifact = Artifact(id=artifact_id, name="index.html")
    version = ArtifactVersion(
        id=str(uuid.uuid4()),
        artifact_id=artifact_id,
        vault_uri="vault://x",
        sha256_hash="hash",
        created_at=datetime.now(UTC),
    )
    artifact.versions = [version]
    files = {"index.html": PublishFile(path="index.html", content="<html/>")}

    with patch(
        "app.services.hosting.orchestrator.resolve_artifact_deploy_files",
        new_callable=AsyncMock,
        return_value=(artifact, files),
    ):
        with patch(
            "app.services.hosting.orchestrator.resolve_target_credentials",
            new_callable=AsyncMock,
            side_effect=RuntimeError("Hosting credentials not configured for this target."),
        ):
            result = await publish_artifact_to_target(
                db_session,
                artifact_id,
                "/tmp/workspace",
                hosting_target_id=LEGACY_VERCEL_TARGET_ID,
            )

    assert result.success is False
    assert result.status == "ERROR"


@pytest.mark.asyncio
async def test_publish_unexpected_value_error_reraises(db_session: AsyncSession) -> None:
    await save_hosting_targets(
        db_session,
        [HostingTarget(id=LEGACY_VERCEL_TARGET_ID, name="Vercel", provider_type="vercel", config={}, is_default=True)],
    )
    with patch(
        "app.services.hosting.orchestrator.resolve_artifact_deploy_files",
        new_callable=AsyncMock,
        side_effect=ValueError("OTHER"),
    ):
        with pytest.raises(ValueError, match="OTHER"):
            await publish_artifact_to_target(
                db_session,
                "art-1",
                "/tmp/workspace",
                hosting_target_id=LEGACY_VERCEL_TARGET_ID,
            )
