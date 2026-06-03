from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from app.database.models.artifact import Artifact, ArtifactVersion


@pytest.fixture
async def mock_artifact(db_session):
    import uuid
    artifact = Artifact(
        id=str(uuid.uuid4()),
        name="test-artifact",
        is_deleted=False
    )
    db_session.add(artifact)
    await db_session.commit()
    await db_session.refresh(artifact)
    
    version = ArtifactVersion(
        id=str(uuid.uuid4()),
        artifact_id=artifact.id,
        vault_uri="test_uri",
        sha256_hash="test_hash"
    )
    db_session.add(version)
    await db_session.commit()
    await db_session.refresh(artifact)
    
    return artifact

@pytest.mark.asyncio
async def test_deploy_artifact_success(client, mock_artifact, db_session):
    # Mock Vault reading
    with patch("app.api.files.deploy_api.ArtifactVault") as mock_vault_class:
        mock_vault_instance = mock_vault_class.return_value
        mock_path = AsyncMock()
        mock_path.exists.return_value = True
        mock_path.is_file.return_value = True
        mock_path.suffix = ".html"
        mock_vault_instance.get_object_path.return_value = mock_path
        
        # Mock file reading
        with patch("builtins.open", create=True) as mock_open:
            mock_open.return_value.__enter__.return_value.read.return_value = "<h1>Hello</h1>"
            
            # Mock VercelClient
            with patch("app.api.files.deploy_api.VercelClient") as mock_vercel_class:
                mock_vercel_instance = mock_vercel_class.return_value
                mock_vercel_instance.deploy.return_value = {
                    "deployment_id": "dep_123",
                    "url": "https://test.vercel.app",
                    "project_id": "prj_456",
                    "status": "READY"
                }
                
                # Use async_client instead of sync client for async endpoint
                from httpx import AsyncClient, ASGITransport
                from app.main import app
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                    response = await ac.post(
                        f"/api/v1/artifacts/{mock_artifact.id}/deploy",
                        json={"token": "test_token"}
                    )
                
                assert response.status_code == 200
                data = response.json()
                assert data["deployment_id"] == "dep_123"
                assert data["url"] == "https://test.vercel.app"
                
                # Verify DB update
                await db_session.refresh(mock_artifact)
                assert mock_artifact.deployment_url == "https://test.vercel.app"
                assert mock_artifact.deployment_status == "READY"

@pytest.mark.asyncio
async def test_deploy_artifact_not_found(client):
    response = client.post(
        "/api/v1/artifacts/invalid-id/deploy",
        json={"token": "test_token"}
    )
    assert response.status_code == 404
