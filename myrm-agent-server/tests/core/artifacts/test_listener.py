"""Tests for Artifact listener."""

import os
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from myrm_agent_harness.agent.artifacts.registry import GeneratedFile
from myrm_agent_harness.agent.artifacts.vault import ArtifactVault

from app.core.artifacts.listener import (
    _WALK_SKIP_DIRS,
    persist_artifact_event,
    resolve_sandbox_file_path,
)
from app.database.models.artifact import Artifact, ArtifactVersion


@pytest.fixture
def tmp_workspace(tmp_path: Path) -> str:
    """Provide a temporary workspace directory."""
    return str(tmp_path)


@pytest.mark.asyncio
async def test_persist_artifact_event_raw_file(tmp_workspace: str):
    """Test persisting a raw file from disk uses put_file."""
    # Create a dummy file in the workspace
    file_path = os.path.join(tmp_workspace, "test_file.txt")
    with open(file_path, "w") as f:
        f.write("Hello, World!")

    files = [GeneratedFile(path="test_file.txt")]

    from unittest.mock import MagicMock

    # Mock DB session
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = None
    mock_db.execute.return_value = mock_result

    # Spy on ArtifactVault.put_file
    with patch.object(ArtifactVault, "put_file", wraps=ArtifactVault(tmp_workspace).put_file) as mock_put_file:
        await persist_artifact_event(
            db=mock_db,
            files=files,
            workspace_root=tmp_workspace,
            chat_id="chat_1",
        )

        # Verify put_file was called instead of put
        mock_put_file.assert_called_once()
        args, kwargs = mock_put_file.call_args
        assert kwargs["file_path"] == file_path
        assert kwargs["filename"] == "test_file.txt"

        # Verify DB operations
        assert mock_db.add.call_count == 2  # Artifact and ArtifactVersion

        # Check added models
        added_models = [call.args[0] for call in mock_db.add.call_args_list]
        artifact = next(m for m in added_models if isinstance(m, Artifact))
        version = next(m for m in added_models if isinstance(m, ArtifactVersion))

        assert artifact.name == "test_file.txt"
        assert version.artifact_id == artifact.id
        assert version.vault_uri.startswith("vault://")


class TestWalkSkipDirs:
    """Tests for _WALK_SKIP_DIRS constant."""

    def test_is_frozenset(self):
        assert isinstance(_WALK_SKIP_DIRS, frozenset)

    def test_contains_critical_dirs(self):
        critical = {"node_modules", "__pycache__", ".git", ".venv", "dist", "build"}
        assert critical.issubset(_WALK_SKIP_DIRS)


class TestResolveSandboxFilePath:
    """Tests for resolve_sandbox_file_path."""

    def test_absolute_existing_file(self, tmp_path: Path):
        target = tmp_path / "report.pdf"
        target.write_text("content")
        result = resolve_sandbox_file_path(str(target), str(tmp_path))
        assert result == str(target)

    def test_relative_to_workspace(self, tmp_path: Path):
        target = tmp_path / "output.txt"
        target.write_text("content")
        result = resolve_sandbox_file_path("output.txt", str(tmp_path))
        assert result == str(target)

    def test_chat_id_sandbox_path(self, tmp_path: Path):
        sandbox_dir = tmp_path / "sandboxes" / "chat_123"
        sandbox_dir.mkdir(parents=True)
        target = sandbox_dir / "result.csv"
        target.write_text("data")
        result = resolve_sandbox_file_path("result.csv", str(tmp_path), chat_id="chat_123")
        assert result == str(target)

    def test_fallback_walk_finds_nested_file(self, tmp_path: Path):
        nested = tmp_path / "deep" / "nested"
        nested.mkdir(parents=True)
        target = nested / "found_me.txt"
        target.write_text("here")
        result = resolve_sandbox_file_path("found_me.txt", str(tmp_path))
        assert result == str(target)

    def test_walk_skips_node_modules(self, tmp_path: Path):
        nm = tmp_path / "node_modules" / "package"
        nm.mkdir(parents=True)
        (nm / "hidden.txt").write_text("inside nm")

        result = resolve_sandbox_file_path("hidden.txt", str(tmp_path))
        assert result is None

    def test_walk_skips_pycache(self, tmp_path: Path):
        cache = tmp_path / "__pycache__"
        cache.mkdir()
        (cache / "module.cpython-312.pyc").write_text("bytecode")

        result = resolve_sandbox_file_path("module.cpython-312.pyc", str(tmp_path))
        assert result is None

    def test_walk_skips_venv(self, tmp_path: Path):
        venv = tmp_path / ".venv" / "lib"
        venv.mkdir(parents=True)
        (venv / "deep_lib.so").write_text("binary")

        result = resolve_sandbox_file_path("deep_lib.so", str(tmp_path))
        assert result is None

    def test_walk_skips_dist(self, tmp_path: Path):
        dist = tmp_path / "dist"
        dist.mkdir()
        (dist / "bundle.js").write_text("bundled")

        result = resolve_sandbox_file_path("bundle.js", str(tmp_path))
        assert result is None

    def test_nonexistent_file_returns_none(self, tmp_path: Path):
        result = resolve_sandbox_file_path("does_not_exist.txt", str(tmp_path))
        assert result is None

    def test_prefers_direct_path_over_walk(self, tmp_path: Path):
        direct = tmp_path / "report.txt"
        direct.write_text("direct")
        nested = tmp_path / "sub"
        nested.mkdir()
        (nested / "report.txt").write_text("nested")

        result = resolve_sandbox_file_path("report.txt", str(tmp_path))
        assert result == str(direct)
