"""Tests for local file actions API (reveal / open).

Tests cover:
- Security: local mode enforcement, path traversal prevention, workspace boundary
- Path resolution: sandboxes/ prefix, absolute paths, relative paths
- Platform commands: macOS, Windows, Linux
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.api.files.local_actions import (
    _get_workspace_dir,
    _open_with_default_app,
    _resolve_artifact_path,
    _reveal_in_file_manager,
    _validate_local_mode,
)


class TestValidateLocalMode:
    """Tests for _validate_local_mode security check."""

    def test_raises_403_when_not_local(self):
        with patch("app.config.deploy_mode.is_local_mode", return_value=False):
            with pytest.raises(HTTPException) as exc_info:
                _validate_local_mode()
            assert exc_info.value.status_code == 403

    def test_passes_when_local(self):
        with patch("app.config.deploy_mode.is_local_mode", return_value=True):
            _validate_local_mode()


class TestGetDataDir:
    """Tests for _get_workspace_dir."""

    def test_returns_state_dir_from_settings(self):
        """Test that _get_workspace_dir returns settings.database.state_dir."""
        result = _get_workspace_dir()
        # Should return a valid path (either from MYRM_DATA_DIR or default)
        assert result is not None
        assert isinstance(result, str)
        assert len(result) > 0

    def test_returns_custom_workspace_dir(self):
        """Test that _get_workspace_dir respects MYRM_DATA_DIR setting."""
        from app.config.settings import DatabaseSettings

        custom_dir = "/custom/workspace"
        with patch.dict(os.environ, {"MYRM_DATA_DIR": custom_dir}):
            db_settings = DatabaseSettings()
            assert db_settings.state_dir == custom_dir


class TestResolveArtifactPath:
    """Tests for _resolve_artifact_path path resolution and validation."""

    @pytest.mark.asyncio
    async def test_file_not_found_returns_404(self):
        mock_svc = MagicMock()
        mock_svc.get_file = AsyncMock(return_value=None)

        with patch("app.core.storage.FilesService", return_value=mock_svc):
            with pytest.raises(HTTPException) as exc_info:
                await _resolve_artifact_path("nonexistent_id")
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_no_storage_path_returns_404(self):
        mock_file = MagicMock()
        mock_file.storage_path = ""
        mock_svc = MagicMock()
        mock_svc.get_file = AsyncMock(return_value=mock_file)

        with patch("app.core.storage.FilesService", return_value=mock_svc):
            with pytest.raises(HTTPException) as exc_info:
                await _resolve_artifact_path("file_no_path")
            assert exc_info.value.status_code == 404
            assert "no local path" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_path_outside_workspace_returns_403(self):
        with tempfile.TemporaryDirectory() as workspace:
            outside_file = tempfile.NamedTemporaryFile(delete=False)
            try:
                mock_file = MagicMock()
                mock_file.storage_path = outside_file.name
                mock_svc = MagicMock()
                mock_svc.get_file = AsyncMock(return_value=mock_file)

                with (
                    patch("app.core.storage.FilesService", return_value=mock_svc),
                    patch("app.api.files.local_actions._get_workspace_dir", return_value=workspace),
                ):
                    with pytest.raises(HTTPException) as exc_info:
                        await _resolve_artifact_path("file_outside")
                    assert exc_info.value.status_code == 403
                    assert "outside workspace" in exc_info.value.detail
            finally:
                os.unlink(outside_file.name)

    @pytest.mark.asyncio
    async def test_file_not_exist_on_disk_returns_404(self):
        with tempfile.TemporaryDirectory() as workspace:
            mock_file = MagicMock()
            mock_file.storage_path = "nonexistent_file.txt"
            mock_svc = MagicMock()
            mock_svc.get_file = AsyncMock(return_value=mock_file)

            with (
                patch("app.core.storage.FilesService", return_value=mock_svc),
                patch("app.api.files.local_actions._get_workspace_dir", return_value=workspace),
            ):
                with pytest.raises(HTTPException) as exc_info:
                    await _resolve_artifact_path("file_missing")
                assert exc_info.value.status_code == 404
                assert "does not exist" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_relative_path_resolves_correctly(self):
        with tempfile.TemporaryDirectory() as workspace:
            test_file = Path(workspace) / "test_output.txt"
            test_file.write_text("test content")

            mock_file = MagicMock()
            mock_file.storage_path = "test_output.txt"
            mock_svc = MagicMock()
            mock_svc.get_file = AsyncMock(return_value=mock_file)

            with (
                patch("app.core.storage.FilesService", return_value=mock_svc),
                patch("app.api.files.local_actions._get_workspace_dir", return_value=workspace),
            ):
                result = await _resolve_artifact_path("file_relative")
                assert result == test_file.resolve()

    @pytest.mark.asyncio
    async def test_sandbox_prefix_path_resolves(self):
        with tempfile.TemporaryDirectory() as workspace:
            test_file = Path(workspace) / "output.txt"
            test_file.write_text("sandbox content")

            mock_file = MagicMock()
            mock_file.storage_path = "sandboxes/abc123/output.txt"
            mock_svc = MagicMock()
            mock_svc.get_file = AsyncMock(return_value=mock_file)

            with (
                patch("app.core.storage.FilesService", return_value=mock_svc),
                patch("app.api.files.local_actions._get_workspace_dir", return_value=workspace),
            ):
                result = await _resolve_artifact_path("file_sandbox")
                assert result == test_file.resolve()

    @pytest.mark.asyncio
    async def test_path_traversal_blocked(self):
        with tempfile.TemporaryDirectory() as workspace:
            mock_file = MagicMock()
            mock_file.storage_path = "../../../etc/passwd"
            mock_svc = MagicMock()
            mock_svc.get_file = AsyncMock(return_value=mock_file)

            with (
                patch("app.core.storage.FilesService", return_value=mock_svc),
                patch("app.api.files.local_actions._get_workspace_dir", return_value=workspace),
            ):
                with pytest.raises(HTTPException) as exc_info:
                    await _resolve_artifact_path("file_traversal")
                assert exc_info.value.status_code in (403, 404)


class TestRevealInFileManager:
    """Tests for _reveal_in_file_manager platform commands."""

    def test_darwin_uses_open_r(self):
        path = Path("/workspace/test.txt")
        with patch("app.api.files.local_actions.platform.system", return_value="Darwin"):
            with patch("app.api.files.local_actions.subprocess.Popen") as mock_popen:
                _reveal_in_file_manager(path)
                mock_popen.assert_called_once_with(["open", "-R", str(path)])

    def test_windows_uses_explorer(self):
        path = Path("/workspace/test.txt")
        with patch("app.api.files.local_actions.platform.system", return_value="Windows"):
            with patch("app.api.files.local_actions.subprocess.Popen") as mock_popen:
                _reveal_in_file_manager(path)
                mock_popen.assert_called_once_with(["explorer.exe", f"/select,{path}"])

    def test_linux_uses_xdg_open(self):
        path = Path("/workspace/subdir/test.txt")
        with patch("app.api.files.local_actions.platform.system", return_value="Linux"):
            with patch("app.api.files.local_actions.subprocess.Popen") as mock_popen:
                _reveal_in_file_manager(path)
                mock_popen.assert_called_once_with(["xdg-open", str(path.parent)])

    def test_command_not_found_raises_500(self):
        path = Path("/workspace/test.txt")
        with patch("app.api.files.local_actions.platform.system", return_value="Darwin"):
            with patch("app.api.files.local_actions.subprocess.Popen", side_effect=FileNotFoundError):
                with pytest.raises(HTTPException) as exc_info:
                    _reveal_in_file_manager(path)
                assert exc_info.value.status_code == 500


class TestOpenWithDefaultApp:
    """Tests for _open_with_default_app platform commands."""

    def test_darwin_uses_open(self):
        path = Path("/workspace/report.pdf")
        with patch("app.api.files.local_actions.platform.system", return_value="Darwin"):
            with patch("app.api.files.local_actions.subprocess.Popen") as mock_popen:
                _open_with_default_app(path)
                mock_popen.assert_called_once_with(["open", str(path)])

    def test_linux_uses_xdg_open(self):
        path = Path("/workspace/report.pdf")
        with patch("app.api.files.local_actions.platform.system", return_value="Linux"):
            with patch("app.api.files.local_actions.subprocess.Popen") as mock_popen:
                _open_with_default_app(path)
                mock_popen.assert_called_once_with(["xdg-open", str(path)])

    def test_command_not_found_raises_500(self):
        path = Path("/workspace/test.txt")
        with patch("app.api.files.local_actions.platform.system", return_value="Linux"):
            with patch("app.api.files.local_actions.subprocess.Popen", side_effect=FileNotFoundError):
                with pytest.raises(HTTPException) as exc_info:
                    _open_with_default_app(path)
                assert exc_info.value.status_code == 500
