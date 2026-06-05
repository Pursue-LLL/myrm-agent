"""Integration tests for Artifact listener."""

import os
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from myrm_agent_harness.agent.artifacts.registry import GeneratedFile
from myrm_agent_harness.agent.artifacts.vault import ArtifactVault

from app.core.artifacts.listener import persist_artifact_event
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
