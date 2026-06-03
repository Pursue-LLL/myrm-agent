from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from app.database.models.artifact import Artifact, ArtifactVersion


@pytest.fixture
async def mock_artifact(db_session):
    artifact = Artifact(
        name="test-artifact",
        type="html",
        filename="index.html",
        size=100,
        content_type="text/html",
        is_deleted=False
    )
    db_session.add(artifact)
    await db_session.commit()
    await db_session.refresh(artifact)
    
    version = ArtifactVersion(
        artifact_id=artifact.id,
        version=1,
        vault_uri="test_uri",
        size=100
    )
    db_session.add(version)
    await db_session.commit()
    
    return artifact

@pytest.mark.asyncio
async def test_deploy_artifact_success(async_client: AsyncClient, mock_artifact, db_session):
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
                
                response = await async_client.post(
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
async def test_deploy_artifact_not_found(async_client: AsyncClient):
    response = await async_client.post(
        "/api/v1/artifacts/invalid-id/deploy",
        json={"token": "test_token"}
    )
    assert response.status_code == 404
