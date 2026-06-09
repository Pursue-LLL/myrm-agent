"""Tests for AgentDeployService — the server-side DeployBackend implementation.

Isolated unit tests only; all DB and external calls are mocked.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from myrm_agent_harness.toolkits.deploy.deploy_agent_tools import DeployBackend, DeployResult


def _make_service(workspace: str = "/tmp/workspace"):
    from app.services.deploy.agent_deploy_service import AgentDeployService

    return AgentDeployService(workspace_root=workspace)


def _mock_get_session(mock_db):
    """Create a mock get_session that yields mock_db as async context manager."""

    @asynccontextmanager
    async def _get_session():
        yield mock_db

    return _get_session


class TestProtocolCompliance:
    """AgentDeployService must satisfy the DeployBackend Protocol."""

    def test_is_deploy_backend(self) -> None:
        svc = _make_service()
        assert isinstance(svc, DeployBackend)


class TestPreflight:
    """Test the preflight() method."""

    @pytest.mark.asyncio
    async def test_preflight_delegates_to_run_deploy_preflight(self) -> None:
        svc = _make_service("/workspace")

        preflight_result = MagicMock()
        preflight_result.deployable = True
        preflight_result.message = "OK"

        mock_run = AsyncMock(return_value=preflight_result)
        mock_db = AsyncMock()

        with (
            patch("app.database.connection.get_session", _mock_get_session(mock_db)),
            patch("app.services.deploy.preflight.run_deploy_preflight", mock_run),
        ):
            ok, msg = await svc.preflight("art_001")

        assert ok is True
        assert msg == "OK"
        mock_run.assert_awaited_once_with(mock_db, "art_001", "/workspace")

    @pytest.mark.asyncio
    async def test_preflight_returns_false_when_not_deployable(self) -> None:
        svc = _make_service()

        preflight_result = MagicMock()
        preflight_result.deployable = False
        preflight_result.message = "Artifact has no versions"

        mock_run = AsyncMock(return_value=preflight_result)
        mock_db = AsyncMock()

        with (
            patch("app.database.connection.get_session", _mock_get_session(mock_db)),
            patch("app.services.deploy.preflight.run_deploy_preflight", mock_run),
        ):
            ok, msg = await svc.preflight("art_no_versions")

        assert ok is False
        assert "no versions" in msg.lower()


class TestGetArtifactName:
    """Test get_artifact_name()."""

    @pytest.mark.asyncio
    async def test_returns_name_when_found(self) -> None:
        svc = _make_service()

        mock_row = MagicMock()
        mock_row.scalar_one_or_none.return_value = "My Portfolio"

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_row)

        with patch("app.database.connection.get_session", _mock_get_session(mock_db)):
            name = await svc.get_artifact_name("art_found")

        assert name == "My Portfolio"

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self) -> None:
        svc = _make_service()

        mock_row = MagicMock()
        mock_row.scalar_one_or_none.return_value = None

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_row)

        with patch("app.database.connection.get_session", _mock_get_session(mock_db)):
            name = await svc.get_artifact_name("art_missing")

        assert name is None


class TestExecuteDeploy:
    """Test execute_deploy()."""

    def _build_artifact(self, *, name: str = "Test App", project_id: str | None = None):
        artifact = MagicMock()
        artifact.name = name
        artifact.deployment_project_id = project_id
        artifact.versions = [
            MagicMock(id="v1", created_at=datetime(2025, 1, 1, tzinfo=timezone.utc)),
            MagicMock(id="v2", created_at=datetime(2025, 6, 1, tzinfo=timezone.utc)),
        ]
        return artifact

    @pytest.mark.asyncio
    async def test_successful_deploy(self) -> None:
        svc = _make_service("/workspace")

        artifact = self._build_artifact()
        files = [{"file": "index.html", "data": "<h1>Hi</h1>"}]

        mock_preflight_check = MagicMock()
        mock_preflight_check.deployable = True

        mock_vercel = MagicMock()
        mock_vercel.deploy = AsyncMock(
            return_value={
                "url": "https://test-app.vercel.app",
                "project_id": "prj_123",
                "deployment_id": "dpl_456",
                "status": "READY",
            }
        )

        mock_db = AsyncMock()

        with (
            patch("app.database.connection.get_session", _mock_get_session(mock_db)),
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
            patch.object(svc, "_resolve_token", AsyncMock(return_value="tok_test")),
        ):
            result = await svc.execute_deploy("art_deploy")

        assert isinstance(result, DeployResult)
        assert result.success is True
        assert result.url == "https://test-app.vercel.app"
        assert result.project_id == "prj_123"
        assert artifact.deployment_url == "https://test-app.vercel.app"
        assert artifact.deployment_version_id == "v2"

    @pytest.mark.asyncio
    async def test_preflight_check_failure(self) -> None:
        svc = _make_service("/workspace")

        artifact = self._build_artifact()
        files: list = []

        mock_preflight_check = MagicMock()
        mock_preflight_check.deployable = False
        mock_preflight_check.message = "No deployable files"

        mock_db = AsyncMock()

        with (
            patch("app.database.connection.get_session", _mock_get_session(mock_db)),
            patch(
                "app.services.deploy.artifact_files.resolve_artifact_deploy_files",
                AsyncMock(return_value=(artifact, files)),
            ),
            patch(
                "app.services.deploy.preflight.evaluate_deploy_preflight",
                MagicMock(return_value=mock_preflight_check),
            ),
        ):
            result = await svc.execute_deploy("art_empty")

        assert result.success is False
        assert result.status == "PREFLIGHT_FAILED"
        assert "No deployable files" in result.error

    @pytest.mark.asyncio
    async def test_project_name_sanitization(self) -> None:
        svc = _make_service("/workspace")

        artifact = self._build_artifact(name="My Cool App! @#$")
        files = [{"file": "index.html", "data": "<h1>Hi</h1>"}]

        mock_preflight_check = MagicMock()
        mock_preflight_check.deployable = True

        mock_vercel = MagicMock()
        mock_vercel.deploy = AsyncMock(
            return_value={
                "url": "https://my-cool-app-----.vercel.app",
                "project_id": "prj_789",
                "status": "READY",
            }
        )

        mock_db = AsyncMock()

        with (
            patch("app.database.connection.get_session", _mock_get_session(mock_db)),
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
            patch.object(svc, "_resolve_token", AsyncMock(return_value="tok_test")),
        ):
            result = await svc.execute_deploy("art_special")

        assert result.success is True
        deploy_call_args = mock_vercel.deploy.call_args
        project_name = deploy_call_args.kwargs.get("project_name") or deploy_call_args[1].get(
            "project_name"
        )
        assert "@" not in project_name
        assert "!" not in project_name
        assert "#" not in project_name


class TestResolveToken:
    """Test _resolve_token() logic."""

    @pytest.mark.asyncio
    async def test_no_token_raises_runtime_error(self) -> None:
        svc = _make_service()

        mock_scalars = MagicMock()
        mock_scalars.first.return_value = None

        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        with patch("app.config.deploy_mode.is_sandbox", return_value=False):
            with pytest.raises(RuntimeError, match="Vercel token not configured"):
                await svc._resolve_token(mock_db)

    @pytest.mark.asyncio
    async def test_platform_token_in_sandbox(self) -> None:
        svc = _make_service()

        mock_scalars = MagicMock()
        mock_scalars.first.return_value = None

        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        with (
            patch("app.config.deploy_mode.is_sandbox", return_value=True),
            patch.dict("os.environ", {"VERCEL_PLATFORM_TOKEN": "platform_tok_abc"}),
        ):
            token = await svc._resolve_token(mock_db)

        assert token == "platform_tok_abc"

    @pytest.mark.asyncio
    async def test_stored_token_decrypted(self) -> None:
        svc = _make_service()

        mock_row = MagicMock()
        mock_row.config_value = '{"token": "user_tok_xyz"}'
        mock_row.is_encrypted = False

        mock_scalars = MagicMock()
        mock_scalars.first.return_value = mock_row

        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        token = await svc._resolve_token(mock_db)
        assert token == "user_tok_xyz"

    @pytest.mark.asyncio
    async def test_encrypted_cipher_dict_token(self) -> None:
        """Token stored as encrypted dict with _cipher key."""
        svc = _make_service()

        mock_encryption = MagicMock()
        mock_encryption.decrypt.return_value = '{"token": "decrypted_tok"}'

        mock_row = MagicMock()
        mock_row.config_value = {"_cipher": "encrypted_payload"}
        mock_row.is_encrypted = True

        mock_scalars = MagicMock()
        mock_scalars.first.return_value = mock_row

        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        with patch(
            "app.services.config.encryption.get_encryption_service",
            return_value=mock_encryption,
        ):
            token = await svc._resolve_token(mock_db)

        assert token == "decrypted_tok"
        mock_encryption.decrypt.assert_called_once_with("encrypted_payload")

    @pytest.mark.asyncio
    async def test_empty_token_string_raises(self) -> None:
        """Token value that is empty/whitespace should raise RuntimeError."""
        svc = _make_service()

        mock_row = MagicMock()
        mock_row.config_value = '{"token": "   "}'
        mock_row.is_encrypted = False

        mock_scalars = MagicMock()
        mock_scalars.first.return_value = mock_row

        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        with patch("app.config.deploy_mode.is_sandbox", return_value=False):
            with pytest.raises(RuntimeError, match="Vercel token not configured"):
                await svc._resolve_token(mock_db)


class TestProjectNameEdgeCases:
    """Edge cases for project name sanitization in execute_deploy."""

    @pytest.mark.asyncio
    async def test_empty_name_falls_back_to_id_prefix(self) -> None:
        """Artifact with empty name uses id-based fallback."""
        svc = _make_service("/workspace")

        artifact = MagicMock()
        artifact.name = ""
        artifact.deployment_project_id = None
        artifact.versions = [
            MagicMock(id="v1", created_at=datetime(2025, 1, 1, tzinfo=timezone.utc)),
        ]
        files = [{"file": "index.html", "data": "<h1>Hi</h1>"}]

        mock_preflight_check = MagicMock()
        mock_preflight_check.deployable = True

        mock_vercel = MagicMock()
        mock_vercel.deploy = AsyncMock(
            return_value={
                "url": "https://myrm-artifact-abcd1234.vercel.app",
                "project_id": "prj_fallback",
                "status": "READY",
            }
        )

        mock_db = AsyncMock()

        with (
            patch("app.database.connection.get_session", _mock_get_session(mock_db)),
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
            patch.object(svc, "_resolve_token", AsyncMock(return_value="tok_test")),
        ):
            result = await svc.execute_deploy("abcd1234-rest-of-id")

        assert result.success is True
        deploy_call_args = mock_vercel.deploy.call_args
        project_name = deploy_call_args.kwargs.get("project_name") or deploy_call_args[1].get(
            "project_name"
        )
        assert project_name.startswith("myrm-artifact-")

    @pytest.mark.asyncio
    async def test_special_chars_sanitized_to_dashes(self) -> None:
        """Special characters in artifact name become dashes in project name."""
        svc = _make_service("/workspace")

        artifact = MagicMock()
        artifact.name = "My App! @v2"
        artifact.deployment_project_id = None
        artifact.versions = [
            MagicMock(id="v1", created_at=datetime(2025, 1, 1, tzinfo=timezone.utc)),
        ]
        files = [{"file": "index.html", "data": "<h1>Hi</h1>"}]

        mock_preflight_check = MagicMock()
        mock_preflight_check.deployable = True

        mock_vercel = MagicMock()
        mock_vercel.deploy = AsyncMock(
            return_value={
                "url": "https://my-app---v2.vercel.app",
                "project_id": "prj_san",
                "status": "READY",
            }
        )

        mock_db = AsyncMock()

        with (
            patch("app.database.connection.get_session", _mock_get_session(mock_db)),
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
            patch.object(svc, "_resolve_token", AsyncMock(return_value="tok_test")),
        ):
            result = await svc.execute_deploy("art_san")

        assert result.success is True
        deploy_call_args = mock_vercel.deploy.call_args
        project_name = deploy_call_args.kwargs.get("project_name") or deploy_call_args[1].get(
            "project_name"
        )
        assert all(c.isalnum() or c == "-" for c in project_name)
