import hashlib

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.artifact import Artifact, ArtifactVersion


@pytest.mark.asyncio
async def test_artifact_hash_verification(client: TestClient, db_session: AsyncSession, tmp_path):
    """Test that the artifact API correctly verifies the SHA-256 hash of a file."""
    # 1. Setup mock vault file
    vault_dir = tmp_path / ".myrm" / "vault" / "objects"
    vault_dir.mkdir(parents=True, exist_ok=True)

    test_content = b"Hello, Enterprise Vault!"
    expected_hash = hashlib.sha256(test_content).hexdigest()

    obj_id = "test-uuid-1234"
    file_path = vault_dir / obj_id
    file_path.write_bytes(test_content)

    vault_uri = f"vault://{obj_id}"

    # 2. Insert DB records
    artifact = Artifact(id="art-1", name="Test Doc")
    db_session.add(artifact)
    await db_session.flush()

    version = ArtifactVersion(id="ver-1", artifact_id="art-1", vault_uri=vault_uri, sha256_hash=expected_hash)
    db_session.add(version)
    await db_session.commit()

    # 3. Test verification success
    # Mock get_workspace_root_sync to return tmp_path
    from unittest.mock import patch

    from myrm_agent_harness.agent.artifacts.vault import ArtifactVault

    with (
        patch("app.api.dependencies.get_workspace_root", return_value=tmp_path),
        patch.object(ArtifactVault, "get_object_path", return_value=file_path),
    ):
        response = client.post("/api/v1/files/artifacts/art-1/verify/ver-1")
        assert response.status_code == 200
        data = response.json()
        assert data["is_valid"] is True
        assert data["status"] == "TAMPER_FREE"

    # 4. Test tamper detection
    tampered_content = b"Hacked, Enterprise Vault!"
    file_path.write_bytes(tampered_content)

    with (
        patch("app.api.dependencies.get_workspace_root", return_value=tmp_path),
        patch.object(ArtifactVault, "get_object_path", return_value=file_path),
    ):
        response = client.post("/api/v1/files/artifacts/art-1/verify/ver-1")
        assert response.status_code == 200
        data = response.json()
        assert data["is_valid"] is False
        assert data["status"] == "CORRUPTED"
