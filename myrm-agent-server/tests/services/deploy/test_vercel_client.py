from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.services.deploy.deploy_packager import DeployFile
from app.services.deploy.vercel_client import VercelClient


@pytest.fixture
def vercel_client():
    return VercelClient(token="test_token")


@pytest.mark.asyncio
async def test_deploy_success(vercel_client):
    files = {"index.html": DeployFile(path="index.html", content="<h1>Hello</h1>")}

    # Mock httpx.AsyncClient.post
    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_response.json = lambda: {"id": "dep_123", "url": "test.vercel.app", "projectId": "prj_456", "readyState": "READY"}

    with patch("httpx.AsyncClient.post", return_value=mock_response):
        result = await vercel_client.deploy("test-project", files)

        assert result["deployment_id"] == "dep_123"
        assert result["url"] == "https://test.vercel.app"
        assert result["project_id"] == "prj_456"
        assert result["status"] == "READY"


@pytest.mark.asyncio
async def test_deploy_includes_project_id(vercel_client):
    files = {"index.html": DeployFile(path="index.html", content="<h1>Hello</h1>")}

    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_response.json = lambda: {
        "id": "dep_123",
        "url": "test.vercel.app",
        "projectId": "prj_456",
        "readyState": "READY",
    }

    with patch("httpx.AsyncClient.post", return_value=mock_response) as mock_post:
        await vercel_client.deploy("test-project", files, project_id="prj_existing")

        payload = mock_post.call_args.kwargs["json"]
        assert payload["projectId"] == "prj_existing"


@pytest.mark.asyncio
async def test_deploy_spa_injection(vercel_client):
    files = {"index.html": DeployFile(path="index.html", content="<h1>Hello</h1>")}

    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_response.json = lambda: {"id": "dep_123", "url": "test.vercel.app"}

    with patch("httpx.AsyncClient.post", return_value=mock_response) as mock_post:
        await vercel_client.deploy("test-project", files)

        # Check if vercel.json was injected
        call_args = mock_post.call_args[1]
        payload = call_args["json"]

        file_names = [f["file"] for f in payload["files"]]
        assert "index.html" in file_names
        assert "vercel.json" in file_names


@pytest.mark.asyncio
async def test_deploy_failure_with_retry(vercel_client):
    files = {"index.html": DeployFile(path="index.html", content="<h1>Hello</h1>")}

    # Simulate network error
    with patch("httpx.AsyncClient.post", side_effect=httpx.RequestError("Network error")):
        with pytest.raises(httpx.RequestError):
            await vercel_client.deploy("test-project", files)


@pytest.mark.asyncio
async def test_get_deployment_status_success(vercel_client):
    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_response.json = lambda: {"id": "dep_123", "url": "test.vercel.app", "readyState": "READY"}

    with patch("httpx.AsyncClient.get", return_value=mock_response):
        result = await vercel_client.get_deployment_status("dep_123")

        assert result["id"] == "dep_123"
        assert result["url"] == "https://test.vercel.app"
        assert result["status"] == "READY"


@pytest.mark.asyncio
async def test_get_deployment_status_api_error(vercel_client):
    mock_response = AsyncMock()
    mock_response.status_code = 404
    mock_response.text = "Not found"

    with patch("httpx.AsyncClient.get", return_value=mock_response):
        with pytest.raises(Exception, match="Failed to get deployment status"):
            await vercel_client.get_deployment_status("dep_missing")


@pytest.mark.asyncio
async def test_deploy_api_http_error(vercel_client):
    files = {"index.html": DeployFile(path="index.html", content="<h1>Hello</h1>")}

    mock_response = AsyncMock()
    mock_response.status_code = 401
    mock_response.text = "Unauthorized"

    with patch("httpx.AsyncClient.post", return_value=mock_response):
        with pytest.raises(Exception, match="Vercel deployment failed"):
            await vercel_client.deploy("test-project", files)
