"""Tests for shared Vercel artifact deploy executor."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.deploy.types import DeployResult
from app.services.deploy.vercel_artifact_deploy import (
    execute_vercel_artifact_deploy,
    sanitize_vercel_project_name,
)


def _build_artifact(*, name: str = "Test App", project_id: str | None = None):
    artifact = MagicMock()
    artifact.name = name
    artifact.deployment_project_id = project_id
    artifact.versions = [
        MagicMock(id="v1", created_at=datetime(2025, 1, 1, tzinfo=timezone.utc)),
        MagicMock(id="v2", created_at=datetime(2025, 6, 1, tzinfo=timezone.utc)),
    ]
    return artifact


def _mock_db_for_executor(*, existing_artifact: object | None = None) -> AsyncMock:
    """Mock DB session for the executor's lightweight artifact version check."""
    mock_scalars = MagicMock()
    mock_scalars.first.return_value = existing_artifact
    mock_result = MagicMock()
    mock_result.scalars.return_value = mock_scalars
    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)
    mock_db.commit = AsyncMock()
    return mock_db


class TestSanitizeProjectName:
    def test_special_chars_become_dashes(self) -> None:
        assert sanitize_vercel_project_name("My App! @v2", "art_1") == "my-app---v2"

    def test_empty_name_uses_id_prefix(self) -> None:
        assert sanitize_vercel_project_name("", "abcd1234-rest").startswith("myrm-artifact-")


class TestExecuteVercelArtifactDeploy:
    @pytest.mark.asyncio
    async def test_successful_deploy(self) -> None:
        artifact = _build_artifact()
        files = [{"file": "index.html", "data": "<h1>Hi</h1>"}]
        mock_preflight_check = MagicMock(deployable=True)
        mock_vercel = MagicMock()
        mock_vercel.deploy = AsyncMock(
            return_value={
                "url": "https://test-app.vercel.app",
                "project_id": "prj_123",
                "deployment_id": "dpl_456",
                "status": "READY",
            }
        )
        mock_db = _mock_db_for_executor(existing_artifact=_build_artifact())

        with (
            patch(
                "app.services.deploy.artifact_files.resolve_artifact_deploy_files",
                AsyncMock(return_value=(artifact, files)),
            ),
            patch(
                "app.services.deploy.preflight.evaluate_deploy_preflight",
                MagicMock(return_value=mock_preflight_check),
            ),
            patch(
                "app.services.deploy.vercel_client.VercelClient",
                MagicMock(return_value=mock_vercel),
            ),
        ):
            result = await execute_vercel_artifact_deploy(
                mock_db,
                "art_deploy",
                "/workspace",
                vercel_token="tok_test",
            )

        assert isinstance(result, DeployResult)
        assert result.success is True
        assert result.url == "https://test-app.vercel.app"
        assert result.latest_version_id == "v2"
        assert artifact.deployment_url == "https://test-app.vercel.app"
        assert artifact.deployment_version_id == "v2"

    @pytest.mark.asyncio
    async def test_no_versions_returns_preflight_failed(self) -> None:
        empty_artifact = MagicMock()
        empty_artifact.versions = []
        mock_db = _mock_db_for_executor(existing_artifact=empty_artifact)

        result = await execute_vercel_artifact_deploy(
            mock_db,
            "art_no_versions",
            "/workspace",
            vercel_token="tok_test",
        )

        assert result.success is False
        assert result.status == "PREFLIGHT_FAILED"
        assert result.error == "Artifact has no versions to deploy."

    @pytest.mark.asyncio
    async def test_preflight_check_failure(self) -> None:
        artifact = _build_artifact()
        mock_preflight_check = MagicMock(deployable=False, message="No deployable files")
        mock_db = _mock_db_for_executor(existing_artifact=artifact)

        with (
            patch(
                "app.services.deploy.artifact_files.resolve_artifact_deploy_files",
                AsyncMock(return_value=(artifact, [])),
            ),
            patch(
                "app.services.deploy.preflight.evaluate_deploy_preflight",
                MagicMock(return_value=mock_preflight_check),
            ),
        ):
            result = await execute_vercel_artifact_deploy(
                mock_db,
                "art_empty",
                "/workspace",
                vercel_token="tok_test",
            )

        assert result.success is False
        assert result.status == "PREFLIGHT_FAILED"
        assert result.error == "No deployable files"

    @pytest.mark.asyncio
    async def test_vercel_failure_sets_error_status(self) -> None:
        artifact = _build_artifact()
        files = [{"file": "index.html", "data": "<h1>Hi</h1>"}]
        mock_preflight_check = MagicMock(deployable=True)
        mock_vercel = MagicMock()
        mock_vercel.deploy = AsyncMock(side_effect=Exception("Invalid token"))
        mock_db = _mock_db_for_executor(existing_artifact=_build_artifact())

        with (
            patch(
                "app.services.deploy.artifact_files.resolve_artifact_deploy_files",
                AsyncMock(return_value=(artifact, files)),
            ),
            patch(
                "app.services.deploy.preflight.evaluate_deploy_preflight",
                MagicMock(return_value=mock_preflight_check),
            ),
            patch(
                "app.services.deploy.vercel_client.VercelClient",
                MagicMock(return_value=mock_vercel),
            ),
        ):
            result = await execute_vercel_artifact_deploy(
                mock_db,
                "art_fail",
                "/workspace",
                vercel_token="bad_token",
            )

        assert result.success is False
        assert result.status == "ERROR"
        assert artifact.deployment_status == "ERROR"
        mock_db.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_project_name_sanitization(self) -> None:
        artifact = _build_artifact(name="My Cool App! @#$")
        files = [{"file": "index.html", "data": "<h1>Hi</h1>"}]
        mock_preflight_check = MagicMock(deployable=True)
        mock_vercel = MagicMock()
        mock_vercel.deploy = AsyncMock(
            return_value={
                "url": "https://my-cool-app-----.vercel.app",
                "project_id": "prj_789",
                "status": "READY",
            }
        )
        mock_db = _mock_db_for_executor(existing_artifact=_build_artifact())

        with (
            patch(
                "app.services.deploy.artifact_files.resolve_artifact_deploy_files",
                AsyncMock(return_value=(artifact, files)),
            ),
            patch(
                "app.services.deploy.preflight.evaluate_deploy_preflight",
                MagicMock(return_value=mock_preflight_check),
            ),
            patch(
                "app.services.deploy.vercel_client.VercelClient",
                MagicMock(return_value=mock_vercel),
            ),
        ):
            result = await execute_vercel_artifact_deploy(
                mock_db,
                "art_special",
                "/workspace",
                vercel_token="tok_test",
            )

        assert result.success is True
        project_name = mock_vercel.deploy.call_args.kwargs["project_name"]
        assert "@" not in project_name
        assert "!" not in project_name

    @pytest.mark.asyncio
    async def test_empty_name_falls_back_to_id_prefix(self) -> None:
        artifact = _build_artifact(name="")
        artifact.versions = [
            MagicMock(id="v1", created_at=datetime(2025, 1, 1, tzinfo=timezone.utc)),
        ]
        files = [{"file": "index.html", "data": "<h1>Hi</h1>"}]
        mock_preflight_check = MagicMock(deployable=True)
        mock_vercel = MagicMock()
        mock_vercel.deploy = AsyncMock(
            return_value={
                "url": "https://myrm-artifact-abcd1234.vercel.app",
                "project_id": "prj_fallback",
                "status": "READY",
            }
        )
        mock_db = _mock_db_for_executor(existing_artifact=artifact)

        with (
            patch(
                "app.services.deploy.artifact_files.resolve_artifact_deploy_files",
                AsyncMock(return_value=(artifact, files)),
            ),
            patch(
                "app.services.deploy.preflight.evaluate_deploy_preflight",
                MagicMock(return_value=mock_preflight_check),
            ),
            patch(
                "app.services.deploy.vercel_client.VercelClient",
                MagicMock(return_value=mock_vercel),
            ),
        ):
            await execute_vercel_artifact_deploy(
                mock_db,
                "abcd1234-rest-of-id",
                "/workspace",
                vercel_token="tok_test",
            )

        project_name = mock_vercel.deploy.call_args.kwargs["project_name"]
        assert project_name.startswith("myrm-artifact-")
