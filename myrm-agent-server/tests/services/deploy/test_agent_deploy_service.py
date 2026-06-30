"""Tests for AgentDeployService — the server-side DeployBackend implementation.

Isolated unit tests only; all DB and external calls are mocked.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.deploy.deploy_agent_tools import DeployBackend, DeployResult
from app.services.deploy.types import DeployResult as DomainDeployResult


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
    """Test execute_deploy() delegates to shared executor."""

    @pytest.mark.asyncio
    async def test_delegates_to_shared_executor(self) -> None:
        svc = _make_service("/workspace")
        expected = DomainDeployResult(
            success=True,
            url="https://test-app.vercel.app",
            deployment_id="dpl_456",
            project_id="prj_123",
            status="READY",
            latest_version_id="v2",
        )
        mock_db = AsyncMock()

        with (
            patch("app.database.connection.get_session", _mock_get_session(mock_db)),
            patch(
                "app.services.deploy.credentials.resolve_vercel_token",
                AsyncMock(return_value="tok_test"),
            ),
            patch(
                "app.services.deploy.vercel_artifact_deploy.execute_vercel_artifact_deploy",
                AsyncMock(return_value=expected),
            ) as mock_execute,
        ):
            result = await svc.execute_deploy("art_deploy")

        assert isinstance(result, DeployResult)
        assert result.success is True
        assert result.url == "https://test-app.vercel.app"
        mock_execute.assert_awaited_once_with(
            mock_db,
            "art_deploy",
            "/workspace",
            vercel_token="tok_test",
        )

    @pytest.mark.asyncio
    async def test_missing_token_returns_token_missing(self) -> None:
        svc = _make_service("/workspace")
        mock_db = AsyncMock()

        with (
            patch("app.database.connection.get_session", _mock_get_session(mock_db)),
            patch(
                "app.services.deploy.credentials.resolve_vercel_token",
                AsyncMock(side_effect=RuntimeError("Vercel token not configured")),
            ),
        ):
            result = await svc.execute_deploy("art_no_token")

        assert result.success is False
        assert result.status == "TOKEN_MISSING"
