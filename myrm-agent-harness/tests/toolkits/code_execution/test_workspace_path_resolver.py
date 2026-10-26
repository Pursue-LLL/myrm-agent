"""Tests for intelligent workspace path resolver."""

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from myrm_agent_harness.core.context_vars import workspace_root_var
from myrm_agent_harness.toolkits.code_execution.utils.workspace_path import (
    WorkspacePathResolver,
)


class TestWorkspacePathResolver:
    """Test intelligent workspace root resolution."""

    def setup_method(self):
        """Clear cached workspace root before each test."""
        WorkspacePathResolver._cached_workspace_root = None

    def test_resolve_from_env_var(self, tmp_path):
        """Test: WORKSPACE_ROOT env var takes highest priority."""
        with patch.dict(os.environ, {"WORKSPACE_ROOT": str(tmp_path)}):
            result = WorkspacePathResolver.resolve_workspace_root()
            assert result == tmp_path

    def test_resolve_from_container_workspace(self, tmp_path):
        """Test: Container /workspace detection."""
        with (
            patch.object(Path, "exists", return_value=True),
            patch.object(WorkspacePathResolver, "_is_in_container", return_value=True),
        ):
            result = WorkspacePathResolver.resolve_workspace_root()
            assert result == Path("/workspace")

    def test_resolve_from_project_markers(self, tmp_path):
        """Test: Detect project root from .git marker."""
        # Create .git marker
        (tmp_path / ".git").mkdir()

        with patch("pathlib.Path.cwd", return_value=tmp_path):
            result = WorkspacePathResolver.resolve_workspace_root()
            assert result == tmp_path

    def test_resolve_fallback_to_cwd(self, tmp_path):
        """Test: Fallback to current working directory."""
        # Marker detection walks up through every ancestor of cwd (/tmp on Linux), so pin it to "no marker".
        with (
            patch("pathlib.Path.cwd", return_value=tmp_path),
            patch.dict(os.environ, {}, clear=True),
            patch.object(WorkspacePathResolver, "_detect_project_root", return_value=None),
        ):
            result = WorkspacePathResolver.resolve_workspace_root()
            assert result == tmp_path

    def test_to_local_path_auto_resolve(self, tmp_path):
        """Test: to_local_path auto-resolves workspace_root if None."""
        with patch.object(WorkspacePathResolver, "resolve_workspace_root", return_value=tmp_path):
            result = WorkspacePathResolver.to_local_path("/workspace/test.py", workspace_root=None)
            assert result == tmp_path / "test.py"

    def test_detect_project_root_with_pyproject(self, tmp_path):
        """Test: Detect project root from pyproject.toml."""
        (tmp_path / "pyproject.toml").touch()
        subdir = tmp_path / "subdir"
        subdir.mkdir()

        with patch("pathlib.Path.cwd", return_value=subdir):
            result = WorkspacePathResolver._detect_project_root()
            assert result == tmp_path

    def test_is_in_container_dockerenv(self):
        """Test: Container detection via /.dockerenv."""
        with patch.object(Path, "exists", side_effect=lambda: True):
            assert WorkspacePathResolver._is_in_container()

    def test_is_in_container_k8s(self):
        """Test: Container detection via K8S env var."""
        with patch.dict(os.environ, {"KUBERNETES_SERVICE_HOST": "127.0.0.1"}):
            assert WorkspacePathResolver._is_in_container()

    def test_generate_diagnostics(self, tmp_path):
        """Test: Diagnostic information generation."""
        with patch("pathlib.Path.cwd", return_value=tmp_path):
            diagnostics = WorkspacePathResolver._generate_diagnostics()

            assert "cwd" in diagnostics
            assert "is_container" in diagnostics
            assert "detected_markers" in diagnostics
            assert diagnostics["cwd"] == str(tmp_path)

    def test_caching_workspace_root(self, tmp_path):
        """Test: Workspace root is cached after first resolution."""
        with (
            patch("pathlib.Path.cwd", return_value=tmp_path),
            patch.object(WorkspacePathResolver, "_detect_project_root", return_value=None),
        ):
            result1 = WorkspacePathResolver.resolve_workspace_root()
            result2 = WorkspacePathResolver.resolve_workspace_root()

            assert result1 == result2
            assert WorkspacePathResolver._cached_workspace_root == tmp_path


class TestRunBoundWorkspaceRoot:
    """The root bound to the active run outranks every process-level signal."""

    @pytest.fixture(autouse=True)
    def _isolate(self):
        WorkspacePathResolver.reset_cache()
        token = workspace_root_var.set("")
        yield
        workspace_root_var.reset(token)
        WorkspacePathResolver.reset_cache()

    def test_bound_root_beats_env_and_cwd(self, tmp_path, monkeypatch):
        chat_ws = tmp_path / "chat_ws"
        chat_ws.mkdir()
        other = tmp_path / "other"
        other.mkdir()
        monkeypatch.chdir(other)
        monkeypatch.setenv("WORKSPACE_ROOT", str(other))

        workspace_root_var.set(str(chat_ws))

        assert WorkspacePathResolver.resolve_workspace_root() == chat_ws

    def test_bound_root_bypasses_process_cache(self, tmp_path, monkeypatch):
        cached = tmp_path / "cached"
        cached.mkdir()
        chat_ws = tmp_path / "chat_ws"
        chat_ws.mkdir()
        monkeypatch.setenv("WORKSPACE_ROOT", str(cached))
        assert WorkspacePathResolver.resolve_workspace_root() == cached

        token = workspace_root_var.set(str(chat_ws))
        try:
            assert WorkspacePathResolver.resolve_workspace_root() == chat_ws
        finally:
            workspace_root_var.reset(token)

        assert WorkspacePathResolver.resolve_workspace_root() == cached

    def test_bound_root_does_not_poison_cache(self, tmp_path, monkeypatch):
        chat_ws = tmp_path / "chat_ws"
        chat_ws.mkdir()
        fallback = tmp_path / "fallback"
        fallback.mkdir()
        monkeypatch.setenv("WORKSPACE_ROOT", str(fallback))

        token = workspace_root_var.set(str(chat_ws))
        try:
            WorkspacePathResolver.resolve_workspace_root()
        finally:
            workspace_root_var.reset(token)

        assert WorkspacePathResolver.resolve_workspace_root() == fallback


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
